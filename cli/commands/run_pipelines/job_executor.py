import concurrent.futures
import glob
import logging
import os
import shutil
import subprocess
import tempfile
import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Set

import click
import git

from cli.commands.run_pipelines.data_models import (
    JobConfig,
    ExecutionMode,
    PipelineConfig,
    RepositoryContext,
    StageConfig
)
from cli.commands.run_pipelines.path_reader import PipelineConfigParser
from cli.commands.run_pipelines.pipeline_validation import PipelineValidator
from cli.utils.thread_safe_counter import ThreadSafeCounter
from cli.utils.constants import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_FILES
from cli.utils.parallel_pipeline_run import (
    resolve_variables,
    ensure_default_registry,
    preprocess_commands,
    image_exists_locally,
    pull_docker_image,
    build_docker_command,
)
from cli.utils.server_client import (
    update_stage,
    create_stage,
    update_job,
    create_job,
    create_repo,
    create_pipeline_run,
    create_pipeline,
    update_pipeline_run,
    get_max_pipeline_run_number
)

logger = logging.getLogger(__name__)


# ============= Executors =============


class PipelineExecutor:
    """
    Responsible for executing a pipeline, managing stages, and ensuring job dependencies are met.

    Attributes:
        pipeline_config (PipelineConfig): The configuration for the pipeline being executed.
        parser (cli.commands.run_pipelines.path_reader.PipelineConfigParser): Parses the pipeline configuration.
        completed_jobs (Set[str]): A set of job names that have been completed.
        job_builder (cli.commands.run_pipelines.path_reader.JobConfigBuilder):
                Builds job configurations from the pipeline configuration.
        pipeline_run_number_counter (ThreadSafeCounter): Counter to track pipeline runs.
        stage_run_number_counter (ThreadSafeCounter): Counter to track stage runs.
        job_run_number_counter (ThreadSafeCounter): Counter to track job runs.
    """
    def __init__(self, pipeline_config: PipelineConfig) -> None:
        """
        Initialize the PipelineExecutor.

        Args:
            pipeline_config (PipelineConfig): The configuration for the pipeline to execute.
        """
        self.pipeline_config = pipeline_config
        self.parser = PipelineConfigParser(pipeline_config)
        self.completed_jobs: Set[str] = set()
        self.job_builder = self.parser.job_builder
        self.job_run_number_counter = ThreadSafeCounter()
        self.stage_run_number_counter = ThreadSafeCounter()
        self.pipeline_run_number_counter = ThreadSafeCounter()

    def _can_execute_job(self, job: JobConfig, completed_jobs: Set[str]) -> bool:
        """
        Check if a job can be executed based on its dependencies.

        Args:
            job (JobConfig): The job to check.
            completed_jobs (Set[str]): A set of completed job names.

        Returns:
            bool: True if all dependencies are completed or if there are no dependencies; False otherwise.
        """
        return not job.needs or all(dep in completed_jobs for dep in job.needs)

    def _execute_job(self, job: JobConfig, stage_id: int) -> None:
        """Execute a single job within a pipeline stage."""
        logger.debug(f"############# Executing job: {job.name} #############")

        try:
            # Create all necessary directories
            for path in filter(None, [
                    job.paths.build_path,
                    job.paths.docs_path,
                    job.paths.logs_path,
                    job.paths.deploy_path,
            ]):

                os.makedirs(path, exist_ok=True)

            if job.artifacts_config:
                os.makedirs(job.artifacts_config.destination_path, exist_ok=True)

            logger.debug(f"Starting job: '{job.name}'")
            global_vars = {}

            image = job.image
            if not image:
                image = global_vars.get("image")
            if not image:
                logger.error(
                    f"No Docker image specified for job '{job.name}'. "
                    f"Job will not be executed."
                )
                return

            image = resolve_variables(image, global_vars)
            if job.registry:
                image = f"{job.registry}/{image}"
            else:
                image = ensure_default_registry(image)

            commands = job.commands
            if not commands:
                logger.error(
                    f"No commands specified for job '{job.name}'. "
                    f"Job will not be executed."
                )
                return

            start_time = datetime.datetime.now().isoformat()
            job_run_number = self.job_run_number_counter.increment()

            job_id = create_job(
                stage_id=stage_id,
                status=2,  # running
                allow_failure=job.allow_failure,
                run_number=job_run_number,
                start_time=start_time,
                end_time=start_time  # Will be updated later
            )

            try:
                if not image_exists_locally(image):
                    pull_docker_image(image)

                commands = preprocess_commands(commands, job.__dict__, global_vars)
                docker_cmd = build_docker_command(
                    image,
                    commands,
                    job.name,
                    job.__dict__,
                    self.pipeline_config.repo_local_path,
                )

                subprocess.run(docker_cmd, check=True)
                logger.info(f"Job '{job.name}' completed successfully.")
                end_time = datetime.datetime.now().isoformat()
                job_status = 3  # 'completed'

            except subprocess.CalledProcessError as e:
                logger.error(f"Job '{job.name}' failed with error: {e}")
                end_time = datetime.datetime.now().isoformat()
                job_status = 4  # 'failed'
                if not job.allow_failure:
                    raise

            finally:
                if job_id:
                    try:
                        update_job(job_id, job_status, end_time)
                    except Exception as e:
                        logger.error(f"Error updating job in database: {e}")

        except Exception as e:
            if not job.allow_failure:
                raise
            logger.warning(f"Job {job.name} failed but continuing: {e}")

    @contextmanager
    def cd(self, path):
        """
        Context manager for temporarily changing the working directory.

        Args:
            path (str): The path to switch to as the current working directory.

        Yields:
            None: Restores the original working directory upon exiting the context.
        """
        old_path = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(old_path)

    def _execute_local_commands(self, job: JobConfig, work_dir: str) -> None:
        """
        Execute local shell commands for a given job within a specified working directory.

        Args:
            job (JobConfig): The job containing the commands to execute.
            work_dir (str): The directory in which the commands should be executed.

        Raises:
            Exception: If a command fails and `allow_failure` is set to False,
                       an exception is raised with the error message.
        """
        with self.cd(work_dir):
            for command in job.commands:
                logger.debug(f"Executing: {command}")
                result = subprocess.run(
                    command,
                    shell=True,
                    check=not job.allow_failure,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise Exception(f"Command failed: {result.stderr}")

    def _execute_docker_commands(self, job: JobConfig, work_dir: str = None) -> None:
        """
        Execute Docker commands for a job, optionally using a specified working directory.

        Args:
            job (JobConfig): The job containing the commands to execute and Docker image details.
            work_dir (Optional[str]): The local directory to mount as the working directory
                                      inside the Docker container. Defaults to the current working directory.

        Raises:
            Exception: If pulling the Docker image or running a command fails and `allow_failure` is set to False.
        """
        image = f"{job.registry}/{job.image}" if job.registry else job.image

        # Use current directory as default work_dir if none is specified
        if work_dir is None:
            work_dir = os.getcwd()

        # Ensure the Docker image is pulled
        logger.debug(f"Pulling Docker image: {image}")
        pull_cmd = ["docker", "pull", image]
        pull_result = subprocess.run(
            pull_cmd, check=True, capture_output=True, text=True
        )
        if pull_result.returncode != 0:
            raise Exception(f"Failed to pull Docker image: " f"{pull_result.stderr}")

        # Execute each command in the pulled Docker image
        for command in job.commands:
            logger.debug(f"Executing in Docker: {command}")
            docker_cmd = [
                "docker",
                "run",
                "--rm",
                # Mount the work_dir to /workspace in the container
                "-v",
                f"{work_dir}: /workspace",
                "-w",
                "/workspace",  # Set the working directory inside the container
                image,
                "sh",
                "-c",
                command,
            ]
            try:
                result = subprocess.run(
                    docker_cmd,
                    check=not job.allow_failure,
                    capture_output=True,
                    text=True,
                )
                logger.info(f"Docker command output: {result.stdout.strip()}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Docker command failed: {e.stderr.strip()}")
                if not job.allow_failure:
                    raise Exception(f"Docker command failed: " f"{e.stderr.strip()}")

    def _collect_artifacts(self, job: JobConfig, work_dir: str) -> None:
        """
        Collect artifacts from the job's working directory based on defined patterns.

        Args:
            job (JobConfig): The job containing artifact configuration.
            work_dir (str): The working directory where artifacts are stored.

        Raises:
            FileNotFoundError: If specified paths or directories do not exist.
        """
        logger.debug("Collecting artifacts...")

        if not job.artifacts_config:
            logger.info("No artifacts configuration found for the job.")
            return

        for pattern in job.artifacts_config.upload_paths:
            full_pattern = os.path.join(work_dir, pattern)
            for file_path in glob.glob(full_pattern, recursive=True):
                src = Path(file_path)
                # If src is file
                if src.is_file():
                    # Calculate the destination path
                    dest = Path(
                        job.artifacts_config.destination_path
                    ) / src.relative_to(work_dir)
                    # Create the destination directory
                    os.makedirs(dest.parent, exist_ok=True)
                    # Copy the file
                    shutil.copy2(src, dest)
                    logger.debug(f"Copied file: {src} -> {dest}")
                # If src is directory
                elif src.is_dir():
                    # Calculate the destination directory
                    dest = Path(
                        job.artifacts_config.destination_path
                    ) / src.relative_to(work_dir)
                    # Copy the entire directory
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                    logger.debug(f"Copied directory: {src} -> {dest}")

    def _execute_stage(self, stage: StageConfig, jobs: List[JobConfig]) -> None:
        """
        Execute all jobs within a single pipeline stage.

        Args:
            stage (StageConfig): The stage containing jobs to execute.
            jobs (List[JobConfig]): A list of all jobs defined in the pipeline.

        Raises:
            click.UsageError: If a job fails and `allow_failure` is set to False.
        """
        logger.debug(f"\nProcessing stage: {stage.name}")

        # Find all jobs associated with the current stage
        stage_jobs = [job for job in jobs if job.stage == stage.name]
        if not stage_jobs:
            logger.info(f"No jobs found for stage: {stage.name}")
            return

        # Execute each job in the stage
        for job in stage_jobs:
            try:
                # Check dependencies
                if not self._can_execute_job(job, self.completed_jobs):
                    msg = f"Job {job.name} has unmet dependencies: {job.needs}"
                    if job.allow_failure:
                        logger.warning(msg)
                        continue
                    raise click.UsageError(msg)

                # Execute the job
                self._execute_job(job)
                self.completed_jobs.add(job.name)

            except Exception as e:
                if not job.allow_failure:
                    raise click.UsageError(f"Job {job.name} failed: {str(e)}")
                logger.warning(
                    f"Job {job.name} failed but continuing due "
                    f"to allow_failure=True: {str(e)}"
                )

    def _execute_pipeline(self, pipeline_config: PipelineConfig) -> None:
        """Execute a complete pipeline based on provided configuration.

        The execution follows this hierarchy:
        Pipeline
        └── Configurations (multiple files)
            └── For each configuration:
                ├── Determine stage execution order
                ├── Prepare all required jobs
                └── For each stage:
                    └── For each job in stage:
                        ├── Validate dependencies
                        ├── Execute job
                        └── Track and update status

        Args:
            pipeline_config: Complete pipeline configuration including repo and execution settings

        Raises:
            DatabaseError: If there's an error interacting with the database
            ConfigurationError: If there's an error in pipeline configuration
            ExecutionError: If there's an error during pipeline execution

        Note:
            - Jobs within the same stage level are executed in parallel
            - Pipeline execution stops if a non-allowed-failure job fails
            - All status updates are persisted to the database
        """
        parser = PipelineConfigParser(pipeline_config)
        # global_vars = extract_global_vars(pipeline_config.configs)

        try:
            # Create repository in the database
            repo_id = create_repo(
                repo_url=pipeline_config.repo_original_path,
                is_local=pipeline_config.execution_mode == ExecutionMode.LOCAL,
            )
        except Exception as e:
            logger.error(f"Error creating repo in database: {e}")
            raise

        # Build dependency chains for all configurations
        dependency_chains = parser.build_dependency_chains(pipeline_config.configs)

        for file_jobs in dependency_chains:
            for file_path, file_data in file_jobs.items():
                logger.debug(f"Scheduling jobs for '{file_path}': ")

                # Extract pipeline_name and dependency chains
                pipeline_name = file_data.get("pipeline_name", "Unnamed Pipeline")
                dependency_chains = file_data.get("dependency", [])
                commit_hash = pipeline_config.git_commit_hash
                pipeline_run_number = get_max_pipeline_run_number(pipeline_name, commit_hash) + 1

                try:
                    pipeline_id = create_pipeline(
                        repo_id=repo_id, pipeline_name=pipeline_name
                    )
                except Exception as e:
                    logger.error(f"Error creating pipeline in database: {e}")
                    raise

                try:
                    pipeline_run_id = create_pipeline_run(
                        pipeline_id=pipeline_id,
                        run_number=pipeline_run_number,
                        git_commit_hash=commit_hash,
                        status=2,  # 'running'
                        start_time=datetime.datetime.now().isoformat(),
                        end_time=datetime.datetime.now().isoformat(),  # Will be updated later
                    )
                except Exception as e:
                    logger.error(f"Error creating pipeline run in database: {e}")
                    raise

                pipeline_failed = (
                    False  # Flag to track if any stage fails or pipeline is terminated
                )
                # Flag to track if pipeline was terminated due to a job failure
                pipeline_terminated = False

                # Execute stages in order
                for stage_info in dependency_chains:
                    if pipeline_terminated:
                        break  # Exit the loop if pipeline is terminated

                    stage_name = stage_info.get("stage")
                    logger.debug(f"\n\tFunction Name: '_execute_pipeline' ######## Executing stage:"
                                 f"'{stage_name}' ######## ")

                    # Record the start time for the stage
                    stage_start_time = datetime.datetime.now().isoformat()
                    stage_status_code = 2  # 'running'
                    stage_run_number = self.stage_run_number_counter.increment()
                    # Create the stage in the database
                    stage_id = None
                    try:
                        stage_id = create_stage(
                            pipeline_run_id=pipeline_run_id,
                            stage_name=stage_name,
                            status=stage_status_code,
                            run_number=stage_run_number,  # Adjust run_number as needed
                            start_time=stage_start_time,
                            end_time=stage_start_time,  # Will be updated later
                        )
                    except Exception as e:
                        logger.error(
                            f"Error creating stage '{stage_name}' in database: {e}"
                        )
                        pipeline_failed = True
                        pipeline_terminated = True
                        break  # Terminate the pipeline

                    stage_failed = False  # Flag to track if any job in the stage fails
                    stage_terminated = False  # Flag to track if stage was terminated due to a job failure

                    # Get the jobs organized by levels within the stage
                    stage_jobs_levels = stage_info.get("jobs", [])

                    # Execute jobs level by level within the stage
                    for level_index, level_jobs in enumerate(stage_jobs_levels):
                        if stage_terminated:
                            break  # Exit the loop if stage is terminated

                        logger.info(f"Level {level_index}: Running jobs in parallel")

                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            futures = []
                            for job_dict in level_jobs:
                                job_name, job_data = next(iter(job_dict.items()))
                                job_config = self.job_builder.build_job_config(
                                    file_path, job_name
                                )
                                future = executor.submit(
                                    self._execute_job,
                                    job_config,
                                    stage_id,
                                )
                                futures.append((future, job_name, job_data))

                            # Wait for all jobs in this level to complete
                            for future, job_name, job_data in futures:
                                try:
                                    future.result()
                                    logger.info(
                                        f"Job '{job_name}' in stage "
                                        f"'{stage_name}' completed successfully."
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Job '{job_name}' in stage '{stage_name}' "
                                        f"failed with exception: {e}"
                                    )
                                    allow_failure = job_data.get("allow_failure", False)
                                    if not allow_failure:
                                        stage_failed = True
                                        stage_terminated = True
                                        pipeline_failed = True
                                        pipeline_terminated = True
                                        break  # Terminate the pipeline

                    # Update the stage status
                    stage_end_time = datetime.datetime.now().isoformat()
                    if stage_failed:
                        stage_status_code = 4  # 'failed'
                    else:
                        stage_status_code = 3  # 'completed'
                    try:
                        update_stage(
                            stage_id=stage_id,
                            status=stage_status_code,
                            end_time=stage_end_time,
                        )
                    except Exception as e:
                        logger.error(
                            f"Error updating stage '{stage_name}' in database: {e}"
                        )

                    if pipeline_terminated:
                        break  # Exit the stages loop if pipeline is terminated

                # After all stages are completed or pipeline is terminated, update the pipeline run status
                pipeline_run_end_time = datetime.datetime.now().isoformat()
                try:
                    if pipeline_failed:
                        pipeline_run_status = 4  # 'failed'
                    elif pipeline_terminated:
                        pipeline_run_status = 5  # 'terminated'
                    else:
                        pipeline_run_status = 3  # 'completed'
                    update_pipeline_run(
                        pipeline_run_id, pipeline_run_status, pipeline_run_end_time
                    )
                except Exception as e:
                    logger.error(f"Error updating pipeline run in database: {e}")

                if pipeline_terminated:
                    logger.error("Pipeline execution terminated due to job failure.")
                    break  # Exit the file_jobs loop if pipeline is terminated

        # print("Pipeline execution completed successfully.")


class PipelineRunner:
    """
    Manages the preparation and execution of CI/CD pipelines.

    Attributes:
        config_dir (str): The custom or default configuration directory.
        pipeline_validator (PipelineValidator): Validates pipeline configurations.
        repo_context (Optional[cli.commands.run_pipelines.data_models.RepositoryContext]):
            Stores repository context information.
    """

    def __init__(self, config_dir: str = None):
        """
        Initialize PipelineRunner.

        Args:
            config_dir (Optional[str]): Custom configuration directory (must start with '.').
                                         Defaults to DEFAULT_CONFIG_DIR.

        Raises:
            click.UsageError: If the custom configuration directory does not start with '.'.
        """
        if config_dir and not config_dir.startswith("."):
            raise click.UsageError(
                "Configuration directory must be hidden (start with '.')"
            )
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self.pipeline_validator = PipelineValidator()
        self.repo_context: Optional[RepositoryContext] = None

    def prepare_pipeline(
        self,
        repo: str = ".",
        branch: str = "main",
        commit: str = "latest",
        pipeline: Optional[str] = None,
        config_file: Optional[str] = None,
        overrides: Optional[List[str]] = None,
        local: bool = True,
    ) -> PipelineConfig:
        """
        Prepare pipeline for execution

        If --repo is not provided and the command is executed inside
        a directory that is version controlled with Git, use the local repository.

        Args:
            repo (str): Repository URL or local path. Defaults to the current directory.
            branch (str): Branch name. Defaults to 'main'.
            commit (str): Commit hash (full or short) or 'latest'. Defaults to 'latest'.
            pipeline (Optional[str]): Name of the pipeline to run. Defaults to None.
            config_file (Optional[str]): Path to the specific configuration file. Defaults to None.
            overrides (Optional[List[str]]): List of `key=value` pairs to override in configs. Defaults to None.
            local (bool): Whether to run the pipeline locally. Defaults to True.

        Returns:
            PipelineConfig: The prepared pipeline configuration.

        Raises:
            click.UsageError: If any step of the preparation process fails.
        """
        try:
            # Step 1: Prepare the repository
            try:
                self.repo_context = self._prepare_repository(repo)
            except click.UsageError as e:
                raise click.UsageError(f"Failed to prepare repository: {str(e)}")

            # Step 2: Validate and switch to the specified branch and commit
            self._checkout_version(branch, commit)

            # Step 3: Find the configuration directory
            config_dir = self._find_config_directory(self.repo_context.local_path)
            if not config_dir:
                raise click.UsageError(
                    "Could not find configuration directory in repository"
                )

            # Step 4: Load and validate pipeline configuration with overrides and validate
            configs_dict = self.load_validate_pipeline_config(
                pipeline=pipeline, config_file=config_file, overrides=overrides
            )

            # Step 5: Return the prepared pipeline configuration
            commit_hash = self.repo_context.repo.head.commit.hexsha
            logger.info(f"original path: {self.repo_context.original_path}")
            return PipelineConfig(
                repo_local_path=self.repo_context.local_path,
                repo_original_path=self.repo_context.original_path,
                config_dir=str(config_dir),  # The actual configuration file
                configs=configs_dict,
                execution_mode=ExecutionMode.LOCAL if local else ExecutionMode.DOCKER,
                git_commit_hash=commit_hash,
            )

        except Exception as e:
            raise click.UsageError(f"Pipeline preparation failed: {str(e)}")

    def _prepare_repository(self, repo_path: str) -> RepositoryContext:
        """
        Prepare the repository and store its initial state.

        If a local path is provided, it initializes the repository context from the existing Git repository.
        If a remote HTTPS URL is provided, it clones the repository to a temporary
        directory and initializes the context from there.

        Args:
            repo_path (Optional[str]): Path to the local repository or HTTPS URL of the remote repository.
                                       If None, it defaults to the current directory.

        Returns:
            RepositoryContext: A context object containing repository details like local path,
                               original path, Git repository object, and initial branch.

        Raises:
            click.UsageError: If the path is not inside a Git repository or cloning fails.
        """
        # Default to the current directory if repo_path is None
        if repo_path is None:
            repo_path = os.getcwd()

            # Search upwards until the .git directory is found
            while not os.path.isdir(os.path.join(repo_path, ".git")):
                parent_dir = os.path.dirname(repo_path)
                if parent_dir == repo_path:
                    # Reached the root directory without finding a .git folder
                    raise click.UsageError("Not inside a Git repository")
                repo_path = parent_dir

        # Handle remote repositories
        if repo_path.startswith(("http://", "https://")):
            if not repo_path.startswith("https://"):
                raise click.UsageError("Only HTTPS URLs are supported")

            temp_dir = tempfile.mkdtemp()  # temp_dir: (str) file path
            try:
                # Clone the repository into a temporary directory
                repo = git.Repo.clone_from(repo_path, temp_dir)
                initial_branch = repo.active_branch.name

                return RepositoryContext(
                    local_path=temp_dir,
                    is_temporary=True,
                    original_path=repo_path,
                    repo=repo,
                    initial_branch=initial_branch,
                )
            except git.exc.GitCommandError as e:
                shutil.rmtree(temp_dir)
                raise click.UsageError(f"Failed to clone repository: {e}")

        # Handle local repositories
        else:
            repo_path = os.path.abspath(repo_path)
            try:
                # Initialize a Repo object from the local path
                repo = git.Repo(repo_path, search_parent_directories=True)
                initial_branch = repo.active_branch.name

                return RepositoryContext(
                    local_path=repo_path,
                    is_temporary=False,
                    original_path=repo_path,
                    repo=repo,
                    initial_branch=initial_branch,
                )
            except git.exc.InvalidGitRepositoryError:
                raise click.UsageError(f"Not a valid Git repository: {repo_path}")

    def _checkout_version(self, branch: str = "main", commit: str = "latest") -> None:
        """
        Checkout a specific branch and commit in the repository.

        Args:
            branch (str): The branch name to checkout. Defaults to "main".
            commit (str): The commit hash (full or short) or "latest".
                          - "latest": Use the latest commit in the branch.
                          - Specific hash: Checkout the given commit.

        Returns:
            None

        Raises:
            click.UsageError: If the repository is invalid, or if the branch/commit is not found.
        """
        if self.repo_context.repo is None:
            raise click.UsageError("Not a valid Git repository")

        repo = self.repo_context.repo
        original_branch = self.repo_context.initial_branch

        try:
            # Step 1: Fetch updates for remote repositories if the repository is temporary
            # Temporary repositories are cloned for a single pipeline execution.
            if self.repo_context.is_temporary:
                repo.git.fetch("--all")

            # Step 2: Check if the branch exists locally or remotely
            # Get all available branches
            local_exists = branch in [head.name for head in repo.heads]
            remote_exists = any(
                ref.name == f"origin/{branch}" for ref in repo.remotes.origin.refs
            )

            try:
                # Handle branch checkout
                if local_exists:
                    # Case 1: The branch exists locally
                    repo.git.checkout(branch)
                elif remote_exists:
                    # Case 2: The branch doesn't exist locally but exists remotely
                    repo.git.checkout("-b", branch, f"origin/{branch}")
                else:
                    # Case 3: The branch doesn't exist locally or remotely
                    available_branches = [f"Local: {b.name}" for b in repo.heads] + [
                        f"Remote: {r.name}"
                        for r in repo.remotes.origin.refs
                        if not r.name.endswith("/HEAD")
                    ]
                    raise click.UsageError(
                        f"Branch '{branch}' not found. Available branches: \n"
                        + "\n".join(f" - {b}" for b in sorted(available_branches))
                    )
            except git.exc.GitCommandError as e:
                raise click.UsageError(f"Failed to checkout branch '{branch}': {e}")

            # Step 3: Handle commit checkout
            if commit and commit != "latest":
                try:
                    self._checkout_specific_commit(repo, branch, commit)
                except click.UsageError as e:
                    # If commit checkout fails, restore the original branch
                    repo.git.checkout(original_branch)
                    raise e
            else:
                # Update to the latest commit in the branch
                self._update_to_latest(repo, branch)

            # Step 4: Verify the checkout state
            self._verify_checkout_state(repo, branch, commit)

        except Exception as e:
            # Restore the initial state in case of errors
            self._restore_initial_state(repo, original_branch)
            raise click.UsageError(f"Failed to checkout version: {str(e)}")

    def _checkout_specific_commit(
        self, repo: git.Repo, branch: str, commit: str
    ) -> None:
        """
        Checkout a specific commit in the repository, supporting both full and short hashes.

        Args:
            repo (git.Repo): The repository object.
            branch (str): The branch to verify the commit against.
            commit (str): The commit hash (full or short) to checkout.

        Raises:
            click.UsageError: If the commit is not found or cannot be checked out.
        """
        # Attempt direct checkout (suitable for full hashes)
        try:
            repo.git.checkout(commit)
            return
        except git.exc.GitCommandError:
            pass

        # Attempt to resolve short hash to full hash
        try:
            full_hash = repo.git.rev_parse(commit)
            repo.git.checkout(full_hash)
            return
        except git.exc.GitCommandError:
            pass

        # Check if the commit exists in the specified branch
        try:
            branch_commits = [c.hexsha for c in repo.iter_commits(branch)]
            short_hashes = [c[: len(commit)] for c in branch_commits]

            if commit not in (branch_commits | short_hashes):
                raise click.UsageError(
                    f"Commit '{commit}' not found in branch '{branch}'.\n"
                    f"Please ensure the commit exists in this branch."
                )
        except git.exc.GitCommandError:
            raise click.UsageError(
                f"Failed to check commit '{commit}' in branch '{branch}'."
            )

    def _update_to_latest(self, repo: git.Repo, branch: str) -> None:
        """
        Update the repository to the latest commit in the specified branch.

        Args:
            repo (git.Repo): The repository object.
            branch (str): The branch to update.

        Raises:
            click.UsageError: If updating to the latest commit fails.
        """
        try:
            # For temporary repositories, pull the latest updates from the remote
            if self.repo_context.is_temporary:
                repo.git.pull("origin", branch)
            else:
                # For local repositories, ensure the correct branch is checked out
                current_branch = repo.active_branch.name
                if current_branch != branch:
                    repo.git.checkout(branch)
        except git.exc.GitCommandError as e:
            raise click.UsageError(f"Failed to update to latest commit: {e}")

    def _verify_checkout_state(
        self, repo: git.Repo, branch: str, expected_commit: str = None
    ) -> None:
        """
        Verify that the repository is in the expected state after checkout.

        Args:
            repo (git.Repo): The repository object.
            branch (str): The branch to verify.
            expected_commit (Optional[str]): The expected commit hash. Defaults to None.

        Raises:
            click.UsageError: If the repository state does not match the expected state.
        """
        try:
            current_commit = repo.head.commit.hexsha

            # If a specific commit is expected, verify it
            if expected_commit and expected_commit != "latest":
                if not (
                    current_commit.startswith(expected_commit)
                    or expected_commit.startswith(current_commit)
                ):
                    raise click.UsageError(
                        f"Checkout verification failed: \n"
                        f"Expected commit: {expected_commit}\n"
                        f"Current commit: {current_commit[:7]}"
                    )

            # Check for detached HEAD state
            is_detached = repo.head.is_detached
            status_msg = (
                f"Checked out: \n"
                f"  Branch: {branch} ("
                f"{'detached HEAD' if is_detached else 'attached HEAD'})\n"
                f"  Commit: {current_commit[:7]}"
            )
            logger.info(status_msg)

        except Exception as e:
            raise click.UsageError(f"Failed to verify checkout state: {e}")

    def _restore_initial_state(self, repo: git.Repo, original_branch: str) -> None:
        """
        Attempt to restore the repository to its initial state by checking out the original branch.

        Args:
            repo (git.Repo): The repository object.
            original_branch (str): The name of the branch to restore.

        Raises:
            None: Warnings are logged if restoration fails but do not raise exceptions.
        """
        try:
            # If the repository is not in a detached HEAD state and the current branch
            # is not the original branch, switch back to the original branch.
            if not repo.head.is_detached and repo.active_branch.name != original_branch:
                repo.git.checkout(original_branch)
                logger.debug(f"Restored to original branch: {original_branch}")
        except Exception as e:
            logger.error(f"Warning: Failed to restore to original branch: {e}")

    def load_validate_pipeline_config(
        self, pipeline: str = None, config_file: str = None, overrides: List[str] = None
    ) -> List[Dict]:
        """
        Load and validate pipeline configurations from the repository.

        This function supports default `.cicd-pipelines` directory or custom directories.
        If neither `--pipeline` nor `--file` is provided, it:
        - Loads all pipeline configurations.
        - Applies overrides to all configurations.
        - Stops on the first validation error.

        It can:
            1. make --pipeline and --file mutually exclusive
            2. Use PipelineValidator to load and validate YAML
            3. Handle default pipeline configuration if none specified

        Args:
            pipeline (str, optional): The name of the pipeline to load (matches the `name` field in YAML).
                                        Defaults to None.
            config_file (str, optional): Path to the configuration file (absolute/relative).
                                        Defaults to None.
            overrides (List[str], optional): A list of key=value pairs to override in configurations.
                                        Defaults to None.

        Returns:
            List[Dict]: A list of dictionaries containing validated pipeline configurations.

        Raises:
            click.UsageError: If the configuration loading or validation fails.

        Notes:
            File Finding Priority:
            1. If config_file provided:
                - Absolute path
                - Relative to repo root
                - Relative to config directory
            2. If pipeline provided:
                - Search for YAML with matching 'name' field
                - Use pipelineValidator.load_yaml
            3. If neither provided:
                - Try default.yml
                - Try ci.yml
                - Use first YAML found
        """
        if not self.repo_context:
            raise click.UsageError("Repository not prepared")

        try:
            # Ensure --pipeline and --file are mutually exclusive
            if pipeline and config_file:
                raise click.UsageError("Cannot specify both --pipeline and --file")

            # Step 1: Find the configuration directory
            config_dir = self._find_config_directory(self.repo_context.local_path)
            if not config_dir:
                raise click.UsageError(
                    f"Could not find "
                    f"'{self.config_dir}' "
                    f"directory in repository"
                )

            # Step 2: Load all YAML files to check for duplicate pipeline names
            all_yaml_files_paths = list(config_dir.glob("*.yml"))
            if not all_yaml_files_paths:
                raise click.UsageError(f"No YAML files found in {config_dir}")

            all_pipeline_data = []
            for yaml_file_path in all_yaml_files_paths:
                try:
                    config_data = self.pipeline_validator.load_yaml(str(yaml_file_path))
                    all_pipeline_data.append({str(yaml_file_path): config_data})
                except Exception:
                    continue  # Continue to the next file if loading fails
                    # raise click.UsageError(f"Failed to load {yaml_file_path}: {str(e)}")

            # Validate pipeline names across files
            if not self.pipeline_validator._validate_unique_pipeline_names(
                all_pipeline_data
            ):
                raise click.UsageError(
                    "Duplicate pipeline names found. Check validation_report.txt for details"
                )

            # Step 3: Load the requested configuration(s). Now proceed with loading the requested configuration(s)
            configs_to_validate = []

            if config_file:
                # Handle --file
                # Use _resolve_config_file_path to locate the specific file.
                # _resolve_config_file_path will internally call _find_config_directory,
                # so it needs to complete its functionality independently.
                config_path = self._resolve_config_file_path(config_file)
                config_data = self.pipeline_validator.load_yaml(str(config_path))
                configs_to_validate.append({str(config_path): config_data})

            elif pipeline:
                # Handle --pipeline
                # Use _find_pipeline_config to locate the configuration by its name.
                # _find_pipeline_config will again call _find_config_directory.
                config_path = self._find_pipeline_config(pipeline)
                config_data = self.pipeline_validator.load_yaml(str(config_path))
                configs_to_validate.append({str(config_path): config_data})

            else:
                if config_file:
                    # Handle --file
                    # Use _resolve_config_file_path to locate the specific file.
                    # _resolve_config_file_path will internally call _find_config_directory,
                    # so it needs to complete its functionality independently.
                    config_path = self._resolve_config_file_path(config_file)
                    config_data = self.pipeline_validator.load_yaml(str(config_path))
                    configs_to_validate.append({str(config_path): config_data})

                elif pipeline:
                    # Handle --pipeline
                    # Use _find_pipeline_config to locate the configuration by its name.
                    # _find_pipeline_config will again call _find_config_directory.
                    config_path = self._find_pipeline_config(pipeline)
                    config_data = self.pipeline_validator.load_yaml(str(config_path))
                    configs_to_validate.append({str(config_path): config_data})

                else:
                    # Handle all files if no specific pipeline or file is provided
                    # Use the previously located config_dir to process all files.
                    # Load all configuration files, stopping immediately if any error occurs.
                    yaml_files = list(config_dir.glob("*.yml"))
                    if not yaml_files:
                        raise click.UsageError(f"No YAML files found in {config_dir}")

                    for yaml_file in yaml_files:
                        # Do not use try-except; let any errors be raised directly.
                        config_data = self.pipeline_validator.load_yaml(str(yaml_file))
                        configs_to_validate.append({str(yaml_file): config_data})

            # Handle overrides
            if overrides:
                for config_dict in configs_to_validate:
                    for path, config_data in config_dict.items():
                        # Directly modify the original configuration while retaining location information.
                        self._apply_overrides_inplace(config_data, overrides)

            # Validate all configurations, stopping immediately if any error occurs.
            if not self.pipeline_validator.validate_pipelines(configs_to_validate):
                raise click.UsageError(
                    "Pipeline validation failed. Check validation_report.txt for details"
                )

            return configs_to_validate

        except Exception as e:
            raise click.UsageError(f"Failed to load configuration: {str(e)}")

    def _find_config_directory(self, start_path: str) -> Optional[Path]:
        """
        Find the .cicd-pipelines or other configuration directory by traversing upward
        from the given directory until reaching the git root.

        Args:
            start_path (str): Starting directory path.

        Returns:
            Optional[Path]: Path to the configuration directory if found, or None otherwise.

        Raises:
            click.UsageError: If not inside a valid git repository or a git command fails.

        Example:
            Repository structure:
                /my-repo/
                    /.cicd-pipelines/     # Configuration directory
                        ci.yml
                        pr.yml
                    /src/
                        /project/
                            /code/

            # Use Case 1: User runs from /my-repo/src/project/code:
            xx run --file ci.yml

            Execution process:
            1. _find_config_directory('/my-repo/src/project/code')
               - Returns '/my-repo/.cicd-pipelines'

            2. _resolve_config_file_path('ci.yml')
               - Uses the discovered configuration directory.
               - Returns '/my-repo/.cicd-pipelines/ci.yml'

            # Use Case 2: User provides an absolute file path:
            xx run --file /home/user/configs/ci.yml

            Execution process:
            1. _resolve_config_file_path('/home/user/configs/ci.yml')
               - Validates and directly returns the given path.
        """
        try:
            # Step 1: Get the root of the Git repository
            repo = git.Repo(start_path, search_parent_directories=True)
            git_root = Path(repo.git.rev_parse("--show-toplevel"))

            # Step 2: Check potential configuration directory locations
            # 1. Directly in the current directory
            current_dir_config = Path(start_path) / self.config_dir
            if current_dir_config.exists():
                return current_dir_config

            # 2. In the Git root directory
            git_root_config = git_root / self.config_dir
            if git_root_config.exists():
                return git_root_config

            # 3. Anywhere between the current directory and the Git root
            current = Path(start_path)
            while current != git_root:
                config_path = current / self.config_dir
                if config_path.exists():
                    return config_path
                current = current.parent

            # 4. Optionally search all directories under the Git root (might be slow)
            logger.debug("Searching for pipeline configuration directory...")
            for path in git_root.rglob(self.config_dir):
                if path.is_dir() and path.name == self.config_dir:
                    logger.debug(
                        f"Found pipeline configuration at: "
                        f"{path.relative_to(git_root)}"
                    )
                    return path

            return None

        except git.exc.InvalidGitRepositoryError:
            raise click.UsageError("Not inside a git repository")
        except git.exc.GitCommandError as e:
            raise click.UsageError(f"Git error: {e}")

    def _resolve_config_file_path(self, config_file: str) -> Path:
        """
        Resolve the configuration file path for the --file option, taking into account the repository structure.

            Purpose:
                Find the specific configuration file (e.g., `ci.yml`).

            Input:
                - A configuration file name or path.

            Output:
                - The complete path to the specific configuration file.

        Args:
            config_file (str): The name or path of the configuration file.

        Returns:
            Path: The resolved path to the configuration file.

        Raises:
            click.UsageError: If the specified configuration file cannot be found.
        """
        file_path = Path(config_file)

        # If the file path is absolute, use it directly
        if file_path.is_absolute():
            if not file_path.exists():
                raise click.UsageError(f"Configuration file not found: {file_path}")
            return file_path

        # Try the following locations:
        # 1. Relative to the current directory
        current_path = Path(self.repo_context.local_path) / file_path
        if current_path.exists():
            return current_path

        # 2. Relative to the config directory
        config_dir = self._find_config_directory(self.repo_context.local_path)
        if config_dir:
            config_path = config_dir / file_path
            if config_path.exists():
                return config_path

            # If the file does not have a `.yml` extension, try appending `.yml`
            if not file_path.suffix:
                config_path = config_path.with_suffix(".yml")
                if config_path.exists():
                    return config_path

        # If the file cannot be found, raise an error with detailed information
        raise click.UsageError(
            f"Configuration file '{config_file}' not found in: \n"
            f" - Current directory: {Path.cwd()}\n"
            f" - Config directory: {config_dir if config_dir else 'Not found'}"
        )

    def _find_pipeline_config(self, pipeline_name: str = None) -> Path:
        """
        Find a pipeline configuration by name or use default configurations.

        If a `pipeline_name` is provided, this method searches for a configuration file
        matching that name. If no name is specified, it attempts to use default configurations.

        Pipeline Name Search (_find_pipeline_config):
            Input: "T2 pipeline"
            ↓
            Read all .yml files in the configuration directory.
            ↓
            Parse the content of each file.
            ↓
            Check if the `name` field matches the input name.
            ↓
            Return the path of the matching configuration file.

        Args:
            pipeline_name (str): The value of the `name` field in the pipeline configuration
                                 (e.g., "T2 pipeline").

        Returns:
            Path: Path to the matched configuration file.

        Raises:
            click.UsageError: If no matching configuration file is found or if no default configuration is available.
        """
        # Step 1: Locate the configuration directory
        # Supports nested directory structures.
        config_dir = self._find_config_directory(self.repo_context.local_path)
        if not config_dir:
            raise click.UsageError(
                f"Could not find configuration directory "
                f"'{self.config_dir}' in repository"
            )

        # Step 2: If a pipeline name is specified, search for a matching configuration file
        if pipeline_name:
            # Search all YAML files
            available_pipelines = {}  # Store all found pipeline names and file paths

            for yaml_file in config_dir.glob("*.yml"):
                try:
                    data = self.pipeline_validator.load_yaml(str(yaml_file))
                    if data and isinstance(data, dict):
                        name = data.get("name")
                        if name:
                            available_pipelines[name] = yaml_file
                            if name == pipeline_name:
                                return yaml_file
                except Exception as e:
                    # Log the error but continue searching other files
                    logger.error(f"Error parsing {yaml_file}: {e}")
                    continue

            # If no matching pipeline is found, provide useful error information
            if available_pipelines:
                pipelines_list = "\n  - ".join(available_pipelines.keys())
                raise click.UsageError(
                    f"No pipeline found with name: '{pipeline_name}'\n"
                    f"Available pipelines: \n - {pipelines_list}"
                )
            else:
                raise click.UsageError(
                    f"No valid pipeline configurations found in {config_dir}"
                )

        # ToDo: Should the pipeline name always be mandatory?
        # Step 3: If no pipeline name is specified, use default configurations
        else:
            # Try default file names in order of priority
            for default_name in DEFAULT_CONFIG_FILES:
                default_path = config_dir / default_name
                if default_path.exists():
                    logger.debug(f"Using default configuration: {default_name}")
                    return default_path

            # If no default configuration is found, use the first YAML file
            yaml_files = list(config_dir.glob("*.yml"))
            if yaml_files:
                logger.debug(
                    f"Using first found configuration: " f"{yaml_files[0].name}"
                )
                return yaml_files[0]

            # No configuration files found
            raise click.UsageError(
                f"No pipeline configurations found in {config_dir}\n"
                f"Please create at least one YAML configuration file"
            )

    def _apply_overrides_inplace(self, config: Dict, overrides: List[str]) -> None:
        """
        Apply overrides directly to the configuration dictionary.

        This modifies the dictionary in place to preserve location information.

        All configuration files will apply these overrides:

        Example:
            xx run --local \
                --override "global.docker.image=gradle:jdk8" \
                --override "global.registry=my-registry.com"

        Args:
            config (Dict): Configuration dictionary to modify.
            overrides (List[str]): List of override strings in the format "key.subkey=value".

        Raises:
            click.UsageError: If an override string is not in the expected format.
        """
        for override in overrides:
            try:
                # Split the override into keys and value
                key_path, value = override.split("=", 1)
                keys = key_path.split(".")

                # Traverse the configuration hierarchy
                current = config
                for key in keys[:-1]:
                    if key not in current:
                        # Create nested dictionaries if missing
                        current[key] = {}
                    current = current[key]

                # Set the final value
                current[keys[-1]] = value

            except ValueError:
                raise click.UsageError(
                    f"Invalid override format: {override}. "
                    "Expected format: key.subkey=value"
                )

    def execute_pipeline(self, pipeline_config: PipelineConfig) -> None:
        """
        Main entry point for pipeline execution.

        Args:
            pipeline_config (PipelineConfig): The pipeline configuration to execute.

        Example:
            This method delegates execution to the PipelineExecutor class.

        """
        executor = PipelineExecutor(pipeline_config)
        executor._execute_pipeline(pipeline_config)

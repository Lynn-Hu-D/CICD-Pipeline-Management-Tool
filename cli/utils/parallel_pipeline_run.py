import subprocess
import concurrent.futures
import shlex
import os
import re
import datetime
import logging

from cli.utils.server_client import (
    update_stage,
    create_stage,
    update_job,
    create_job,
    create_repo,
    create_pipeline_run,
    create_pipeline,
    update_pipeline_run,
)

# Configure logging
logger = logging.getLogger(__name__)


def extract_global_vars(config):
    global_vars = {}
    for file_dict in config:
        for file_path, data in file_dict.items():
            global_section = data.get("global_vars", {})
            for key, value in global_section.items():
                global_vars[key] = value
    logger.debug(f"Extracted global variables: {global_vars}")
    return global_vars


def resolve_variables(text, variables):
    pattern = re.compile(r'\$\{([^}]+)\}')
    while True:
        match = pattern.search(text)
        if not match:
            break
        full_match = match.group(0)
        var_expression = match.group(1)
        if ':-' in var_expression:
            var_name, default = var_expression.split(':-', 1)
            value = variables.get(var_name.strip(), default.strip())
        else:
            value = variables.get(var_expression.strip(), '')
        text = text.replace(full_match, value)
    # logger.debug(f"Variable resolution: '{text}' -> '{resolved_text}'")
    return text


def ensure_default_registry(image):
    # If the image does not contain a registry (no '/') in the first part, prepend 'docker.io/'
    if "/" not in image.split("/")[0]:
        image = f"docker.io/{image}"
    logger.debug(f"Ensured default registry: {image}")
    return image


def image_exists_locally(image):
    try:
        result = subprocess.run(
            ["docker", "images", "-q", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        exists = bool(result.stdout.strip())
        logger.debug(f"Image {image} exists locally: {exists}")
        return exists
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking image existence: {e}")
        raise


def pull_docker_image(image):
    logger.info(f"Pulling Docker image: {image}")
    try:
        subprocess.run(
            ["docker", "pull", image],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info(f"Successfully pulled image: {image}")
    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to pull image '{image}': {e}"
        logger.error(error_msg)
        raise Exception(error_msg)


def preprocess_commands(commands, job_data, global_vars):
    processed_commands = []
    for cmd in commands:
        processed_cmd = resolve_variables(cmd, global_vars)
        processed_commands.append(processed_cmd)
    logger.debug(f"Preprocessed commands: {processed_commands}")
    return processed_commands


def build_docker_command(image, commands, job_name, job_data, repo_path):
    # Join the commands into a single shell command
    shell_command = " && ".join(commands)
    # Handle artifacts and volumes if necessary
    volumes = []
    artifacts = job_data.get("artifacts", {})
    if artifacts:
        # Assume artifacts are stored in the current working directory
        host_artifacts_dir = os.path.abspath("./artifacts")
        container_artifacts_dir = artifacts.get("destination", {}).get(
            "path", "/artifacts"
        )
        os.makedirs(host_artifacts_dir, exist_ok=True)
        volumes.append(f"{host_artifacts_dir}:{container_artifacts_dir}")
    # Mount the repository into the container
    volumes.append(f"{repo_path}:/app")
    # Build the Docker run command
    docker_command = ["docker", "run", "--rm", "-w", "/app"]
    # Mount volumes
    for volume in volumes:
        docker_command.extend(["-v", volume])
    # Set environment variables if needed
    env_vars = job_data.get("environment", {})
    for key, value in env_vars.items():
        docker_command.extend(["-e", f"{key}={value}"])
    # Use the specified image
    docker_command.append(image)
    # Specify the shell to run the commands
    docker_command.extend(["/bin/sh", "-c", shell_command])
    formatted_cmd = " ".join(shlex.quote(arg) for arg in docker_command)
    logger.debug(f"Built Docker command for job '{job_name}': {formatted_cmd}")
    return docker_command


def run_job_in_docker(job_name, job_data, global_vars, repo_path, stage_id, run_number):
    logger.info(f"Starting job: '{job_name}'")
    # Get the job-level image
    image = job_data.get("image")
    # If no job-level image, get the global image
    if not image:
        image = global_vars.get("image")
    # If still no image, fail the job
    if not image:
        error_msg = f"No Docker image specified for job '{job_name}'"
        logger.error(error_msg)
        raise Exception(error_msg)
    # Resolve variables in the image name
    image = resolve_variables(image, global_vars)
    # Ensure default registry
    image = ensure_default_registry(image)

    commands = job_data.get("commands", [])
    if not commands:
        error_msg = f"No commands specified for job '{job_name}'"
        logger.error(error_msg)
        raise Exception(error_msg)

    # Preprocess commands to resolve variables
    commands = preprocess_commands(commands, job_data, global_vars)
    # Check if the image exists locally; if not, pull it
    if not image_exists_locally(image):
        try:
            pull_docker_image(image)
        except Exception as e:
            logger.error(f"Error pulling image for job '{job_name}': {e}")
            return

    # Record the start time
    start_time = datetime.now().isoformat()

    # Create the job entry in the database with status 'running'
    job_status = 2  # Assuming '2' corresponds to 'running' in your Status table
    allow_failure = job_data.get("allow_failure", False)

    # Create the job in the database
    job_id = None
    try:
        job_id = create_job(
            stage_id=stage_id,
            status=job_status,
            allow_failure=allow_failure,
            run_number=run_number,
            start_time=start_time,
            end_time=start_time  # Initialize end_time; will update later
        )
        logger.info(f"Created job record with ID: {job_id}")
    except Exception as e:
        logger.error(f"Error creating job in database: {e}")
        # Handle the failure as per your requirements

    # Build the Docker command
    docker_cmd = build_docker_command(image, commands, job_name, job_data, repo_path)
    # Execute the Docker command
    try:
        subprocess.run(docker_cmd, check=True)
        logger.info(f"Job '{job_name}' completed successfully.")
        # Update the job status to 'completed' in the database
        end_time = datetime.now().isoformat()
        job_status = 3  # Assuming '3' corresponds to 'completed'
    except subprocess.CalledProcessError as e:
        logger.error(f"Job '{job_name}' failed with error: {e}")
        # Update the job status to 'failed' in the database
        end_time = datetime.now().isoformat()
        job_status = 4  # Assuming '4' corresponds to 'failed'
    finally:
        if job_id:
            try:
                update_job(job_id, job_status, end_time)
            except Exception as e:
                logger.error(f"Error updating job in database: {e}")


def run_jobs_in_docker(dependency_chains, repo_path, is_local, run_number):
    try:
        repo_id = create_repo(repo_url=repo_path, is_local=is_local)
    except Exception as e:
        logger.error(f"Error creating repo in database: {e}")
        raise

    for file_jobs in dependency_chains:
        for file_path, file_data in file_jobs.items():
            logger.info(f"Scheduling jobs for '{file_path}':")

            # Extract pipeline_name, global_vars, and dependency chains
            pipeline_name = file_data.get("pipeline_name", "Unnamed Pipeline")
            global_vars = file_data.get("global_vars", {})
            # stages_defined = file_data.get('stages', [])
            dependency_chains = file_data.get("dependency", [])

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
                    run_number=run_number,
                    status=2,  # 'running'
                    start_time=datetime.datetime.now().isoformat(),
                    end_time=None,  # Will be updated later
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
                logger.info(f"############# Executing stage: '{stage_name}' #############")

                # Record the start time for the stage
                stage_start_time = datetime.datetime.now().isoformat()
                stage_status_code = 2  # 'running'

                # Create the stage in the database
                stage_id = None
                try:
                    stage_id = create_stage(
                        pipeline_run_id=pipeline_run_id,
                        status=stage_status_code,
                        run_number=run_number,
                        start_time=stage_start_time,
                        end_time=None,  # Will be updated later
                    )
                except Exception as e:
                    logger.error(
                        f"Error creating stage '{stage_name}' in database: {e}"
                    )
                    pipeline_failed = True
                    pipeline_terminated = True
                    break  # Terminate the pipeline

                stage_failed = False  # Flag to track if any job in the stage fails
                stage_terminated = (
                    False  # Flag to track if stage was terminated due to a job failure
                )

                # Get the jobs organized by levels within the stage
                stage_jobs_levels = stage_info.get("jobs", [])

                # Execute jobs level by level within the stage
                for level_index, level_jobs in enumerate(stage_jobs_levels):
                    if stage_terminated:
                        break  # Exit the loop if stage is terminated

                    logger.debug(f"Level {level_index}: Running jobs in parallel")

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        futures = []
                        # job_statuses = {}
                        for job_dict in level_jobs:
                            job_name, job_data = next(iter(job_dict.items()))
                            future = executor.submit(
                                run_job_in_docker,
                                job_name,
                                job_data,
                                global_vars,
                                repo_path,
                                stage_id,
                                run_number,
                            )
                            futures.append((future, job_name, job_data))

                        # Wait for all jobs in this level to complete
                        for future, job_name, job_data in futures:
                            try:
                                # result = future.result()
                                logger.info(
                                    f"Job '{job_name}' in stage '{stage_name}' completed successfully."
                                )
                            except Exception as e:
                                logger.error(
                                    f"Job '{job_name}' in stage '{stage_name}' failed with exception: {e}"
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
                    # 'terminated' (Assuming '5' corresponds to 'terminated')
                    pipeline_run_status = 5
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

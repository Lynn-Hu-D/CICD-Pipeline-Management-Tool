# ============= Path Handling =============

import os
from pathlib import Path
from typing import Optional, List, Dict

import click

from cli.commands.run_pipelines.data_models import PathConfig, ArtifactConfig, JobConfig, PipelineConfig
from cli.utils.dependency_utils import handle_dependency
from cli.commands.run_pipelines.pipeline_validation import PipelineValidator


class PathResolver:
    """Handles path-related logic."""

    def __init__(self, repo_path: str) -> None:
        self.repo_path = repo_path

    def get_absolute_path(self, path: Optional[str]) -> Optional[str]:
        """Convert a relative path to an absolute path.

        Args:
            path (Optional[str]): The path to convert.

        Returns:
            Optional[str]: The absolute path or None if the input is None.
        """
        if not path:
            return None
        return os.path.join(self.repo_path, path) if not os.path.isabs(path) else path


class ConfigLoader:
    """Load and manage configuration files."""

    def __init__(self, configs: List[Dict[str, Dict]]) -> None:
        self.configs = configs

    @classmethod
    def load_all_configs(
        cls, config_dir: str, pipeline_validator: PipelineValidator
    ) -> "ConfigLoader":
        """Load all YAML configuration files from a directory and validate them.

        Args:
            config_dir (str): Path to the configuration directory.
            pipeline_validator (PipelineValidator): Validator for configuration files.

        Returns:
            ConfigLoader: An instance of the loader with loaded configurations.

        Raises:
            click.UsageError: If the directory is not found or no YAML files exist.
        """
        configs: List[Dict[str, Dict]] = []
        config_dir_path = Path(config_dir)

        if not config_dir_path.exists():
            raise click.UsageError(f"Configuration directory not found: {config_dir}")

        # Load all YAML files
        yaml_files = list(config_dir_path.glob("*.yml"))
        if not yaml_files:
            raise click.UsageError(f"No YAML files found in {config_dir}")

        # First pass: Load all configurations
        for yaml_file in yaml_files:
            try:
                config_data = pipeline_validator.load_yaml(str(yaml_file))
                configs.append({str(yaml_file): config_data})
            except Exception as e:
                raise click.UsageError(f"Failed to load {yaml_file}: {str(e)}")

        # Create loader instance with loaded configs
        loader = cls(configs)

        # Get all pipeline names for validation
        pipeline_names = loader.get_all_pipeline_names()

        # Validate pipeline names using the validator
        for file_path in pipeline_names:
            pipeline_validator._validate_pipeline(
                file_path, loader.get_config_content(file_path)
            )

        return loader

    def get_global_config(self, file_path: str) -> Dict:
        """Retrieve global configuration from a file.

        Args:
            file_path (str): Path to the configuration file.

        Returns:
            Dict: Global configuration.
        """
        for config_dict in self.configs:
            if file_path in config_dict:
                return config_dict[file_path].get("global", {})
        return {}

    def get_job_config(self, file_path: str, job_name: str) -> Optional[Dict]:
        """Retrieve job configuration from a file.

        Args:
            file_path (str): Path to the configuration file.
            job_name (str): Name of the job.

        Returns:
            Optional[Dict]: Job configuration or None if not found.
        """
        for config_dict in self.configs:
            if file_path in config_dict:
                return config_dict[file_path].get("jobs", {}).get(job_name)
        return None

    def get_all_pipeline_names(self) -> Dict[str, str]:
        """Retrieve pipeline names from all configurations.

        Returns:
            Dict[str, str]: Mapping of file paths to pipeline names.
        """
        pipeline_names: Dict[str, str] = {}
        for config_dict in self.configs:
            for file_path, config in config_dict.items():
                name = config.get("name", "unnamed")
                pipeline_names[file_path] = name
        return pipeline_names

    def get_file_by_pipeline_name(self, pipeline_name: str) -> Optional[str]:
        """Find a configuration file by pipeline name.

        Args:
            pipeline_name (str): Name of the pipeline.

        Returns:
            Optional[str]: File path of the configuration or None if not found.
        """
        for config_dict in self.configs:
            for file_path, config in config_dict.items():
                if config.get("name") == pipeline_name:
                    return file_path
        return None


class JobConfigBuilder:
    """Builds job configurations."""

    def __init__(
        self, path_resolver: PathResolver, config_loader: ConfigLoader
    ) -> None:
        """
        Initialize the JobConfigBuilder.

        Args:
            path_resolver (PathResolver): Resolves paths relative to the repository.
            config_loader (ConfigLoader): Loads and manages configuration files.

        Attributes:
            repo_path (str): The base path of the repository, used to resolve all relative paths
        """
        self.path_resolver = path_resolver
        self.config_loader = config_loader
        self.repo_path = path_resolver.repo_path

    def build_path_config(self, job_data: Dict, global_config: Dict) -> PathConfig:
        """
        Build the path configuration.

        All paths are resolved relative to the repository path.

        Args:
            job_data (Dict): Job-specific configuration.
            global_config (Dict): Global configuration shared across jobs.

        Returns:
            PathConfig: A configuration object containing resolved paths.

        Raises:
            ValueError: If a path cannot be resolved.
        """

        def resolve_path(path: Optional[str]) -> Optional[str]:
            """Resolve a path relative to the repository."""
            if not path:
                return None
            # If the path is absolute, convert it to a relative path
            if os.path.isabs(path):
                try:
                    relative_path = os.path.relpath(path, "/")
                    return os.path.join(self.repo_path, relative_path)
                except ValueError as e:
                    raise ValueError(f"Invalid path: {path}: {e}")
            # If the path is relative, resolve it relative to the repo_path
            return os.path.join(self.repo_path, path)

        return PathConfig(
            build_path=resolve_path(
                job_data.get("build", {}).get("path")
                or global_config.get("build", {}).get("path")
            ),
            docs_path=resolve_path(
                job_data.get("docs", {}).get("path")
                or global_config.get("docs", {}).get("path")
            ),
            logs_path=resolve_path(
                job_data.get("logs", {}).get("path")
                or global_config.get("logs", {}).get("path")
            ),
            deploy_path=resolve_path(
                job_data.get("deploy", {}).get("path")
                or global_config.get("deploy", {}).get("path")
            ),
        )

    def build_artifact_config(
        self, job_data: Dict, global_config: Dict
    ) -> Optional[ArtifactConfig]:
        """
        Build the artifact configuration.

        Ensures artifact paths are under the repository path.

        Args:
            job_data (Dict): Job-specific configuration.
            global_config (Dict): Global configuration shared across jobs.

        Returns:
            Optional[ArtifactConfig]: A configuration object for artifacts or None.
        """
        if "artifacts" not in job_data:
            return None

        artifacts = job_data["artifacts"]
        dest_path = artifacts.get("destination", {}).get("path") or global_config.get(
            "artifacts"
        )

        # Make sure the destination path is under the repo path
        if dest_path:
            if os.path.isabs(dest_path):
                relative_path = os.path.relpath(dest_path, "/")
                dest_path = os.path.join(self.repo_path, relative_path)
            else:
                dest_path = os.path.join(self.repo_path, dest_path)

        return ArtifactConfig(
            destination_path=dest_path,
            # Todo: Artifacts path as relative
            upload_paths=artifacts.get("upload", {}).get("path", []),
        )

    def validate_paths(self, paths: List[Optional[str]]) -> None:
        """
        Validate that all paths are within the repository.

        Args:
            paths (List[Optional[str]]): A list of paths to validate.

        Raises:
            ValueError: If a path is outside the repository.
        """
        repo_path_abs = os.path.abspath(self.repo_path)
        for path in paths:
            if path and not os.path.abspath(path).startswith(repo_path_abs):
                raise ValueError("Path must be within the repository")

    def build_job_config(self, file_path: str, job_name: str) -> JobConfig:
        """
        Build a complete job configuration.

        Args:
            file_path (str): Path to the configuration file.
            job_name (str): Name of the job to build.

        Returns:
            JobConfig: The complete job configuration object.

        Raises:
            ValueError: If the job or its data cannot be found.
        """
        job_data = self.config_loader.get_job_config(file_path, job_name)
        if not job_data:
            raise ValueError(f"Job {job_name} not found in {file_path}")

        global_config = self.config_loader.get_global_config(file_path)

        # Build path configuration and artifact configuration
        paths = self.build_path_config(job_data, global_config)
        artifacts_config = self.build_artifact_config(job_data, global_config)

        # Validate all paths
        self.validate_paths(
            [
                paths.build_path,
                paths.docs_path,
                paths.logs_path,
                paths.deploy_path,
                artifacts_config.destination_path if artifacts_config else None,
            ]
        )

        return JobConfig(
            name=job_name,
            stage=job_data["stage"],
            commands=job_data.get("commands", []),
            image=job_data.get("image") or global_config.get("image"),
            registry=job_data.get("registry") or global_config.get("registry"),
            allow_failure=job_data.get("allow_failure", False),
            needs=job_data.get("needs", []),
            artifacts_config=artifacts_config,
            paths=paths,
        )


class PipelineConfigParser:
    """Manages the parsing process of the entire pipeline configuration."""

    def __init__(self, pipeline_config: PipelineConfig) -> None:
        """
        Initialize the PipelineConfigParser.

        Args:
            pipeline_config (PipelineConfig): The pipeline configuration to parse.
        """
        self.path_resolver = PathResolver(pipeline_config.repo_local_path)
        self.config_loader = ConfigLoader(pipeline_config.configs)
        self.job_builder = JobConfigBuilder(self.path_resolver, self.config_loader)

    def prepare_all_jobs(self, file_path: str, yaml_content: Dict) -> List[JobConfig]:
        """
        Prepare all jobs specified in a configuration file.

        Args:
            file_path (str): The path of the configuration file.
            yaml_content (Dict): The content of the YAML configuration file.

        Returns:
            List[JobConfig]: A list of JobConfig objects prepared from the file.
        """
        jobs: List[JobConfig] = []
        for job_name in yaml_content.get("jobs", {}):
            job_config = self.job_builder.build_job_config(file_path, job_name)
            jobs.append(job_config)
        return jobs

    def build_dependency_chains(self, configs: List[Dict]) -> Dict:
        """
        Build dependency chains for the pipeline jobs.

        Args:
            configs (List[Dict]): A list of configurations.

        Returns:
            Dict: A dictionary representing the dependency chains.
        """
        return handle_dependency(configs)

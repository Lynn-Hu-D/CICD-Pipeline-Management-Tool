# ============= Data Models =============
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict

import git


@dataclass
class ArtifactConfig:
    destination_path: Optional[str] = None
    upload_paths: List[str] = None


@dataclass
class PathConfig:
    """
    Configuration for various paths.
    Store all the directories required in build process
    """

    build_path: Optional[str] = None  # Directory for build outputs
    docs_path: Optional[str] = None  # Directory for generated documentation
    logs_path: Optional[str] = None  # Directory for storing logs
    deploy_path: Optional[str] = None  # Directory for deployment-related files


@dataclass
class JobConfig:
    """Configuration for a job."""

    name: str
    stage: str
    commands: List[str]
    image: Optional[str]
    registry: Optional[str]
    allow_failure: bool
    needs: List[str]
    artifacts_config: Optional[ArtifactConfig]
    paths: PathConfig


class ExecutionMode(Enum):
    """Enum for execution modes."""

    LOCAL = "local"
    DOCKER = "docker"


@dataclass
class PipelineConfig:
    """
    Pipeline configuration with execution details.

    Attributes:
        repo_local_path: Repository local path for executing commands
        repo_original_path: Original repository path
        config_dir: Directory containing pipeline configurations
        configs: List of configuration files and their contents in
                    format [{file_path: yaml_content}, ...]
        execution_mode: Mode of execution (LOCAL/DOCKER)
        git_commit_hash: Git commit hash for this pipeline run
    """

    repo_local_path: str
    repo_original_path: str
    config_dir: str
    configs: List[Dict[str, Dict]]
    execution_mode: ExecutionMode
    artifacts_dir: Optional[str] = None
    git_commit_hash: Optional[str] = None

    @property
    def get_config_files(self) -> List[str]:
        """Get paths of all configuration files.

        Returns:
            List[str]: List of file paths.
        """
        return [list(config.keys())[0] for config in self.configs]

    @property
    def get_pipeline_names(self) -> List[str]:
        """Get names of all pipelines.

        Returns:
            List[str]: List of pipeline names.
        """
        return [
            list(config.values())[0].get("name", "unnamed") for config in self.configs
        ]

    def get_config_content(self, file_path: str) -> Dict:
        """Get the content of a specific configuration file.

        Args:
            file_path (str): The file path of the configuration.

        Returns:
            Dict: Configuration content.

        Raises:
            KeyError: If the file path is not found.
        """
        for config in self.configs:
            if file_path in config:
                return config[file_path]
        raise KeyError(f"Configuration file not found: {file_path}")


@dataclass
class RepositoryContext:
    """
    Represents the context of a repository, including details about its local path,
    origin, and state.

    Attributes:
        local_path (str): The actual local path to the repository.
        is_temporary (bool): Indicates whether the repository is a temporary clone.
        original_path (str): The original path or URL of the repository.
        repo (git.Repo): The Git repository object.
        initial_branch (str): The initial branch of the repository.
    """

    local_path: str
    is_temporary: bool
    original_path: str
    repo: git.Repo
    initial_branch: str


@dataclass
class StageConfig:
    name: str

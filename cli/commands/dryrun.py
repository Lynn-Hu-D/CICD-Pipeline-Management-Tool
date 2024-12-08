import yaml
import click
from pathlib import Path
from typing import Dict, List


def find_config_file(config_file: str) -> str:
    """
    Find the configuration file in the correct location.
    Always check .cicd-pipelines directory first.
    """
    # First check in .cicd-pipelines directory
    cicd_path = Path('.cicd-pipelines') / config_file
    if cicd_path.exists():
        return str(cicd_path)

    # Then check in root directory
    root_path = Path(config_file)
    if root_path.exists():
        return str(root_path)

    # If not found, return the .cicd-pipelines path for error message
    return str(cicd_path)


def load_yaml_file(file_path: str) -> dict:
    """Load and parse YAML file"""
    try:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        click.echo(f"Error: Configuration file not found: {file_path}")
        click.echo(
            "Note: Configuration files should be placed in the .cicd-pipelines directory.")
        return None
    except yaml.YAMLError as e:
        click.echo(f"Error: Invalid YAML format in {file_path}")
        click.echo(str(e))
        return None


def get_jobs_by_stage(config: dict) -> Dict[str, List[dict]]:
    """
    Organize jobs by their stages and determine execution order.
    Returns a dictionary with stage names as keys and lists of jobs as values.
    """
    stages_dict = {}

    # First, collect all jobs and their stages
    for job_name, job_config in config.get('jobs', {}).items():
        # Determine which stage this job belongs to
        if 'needs' in job_config:
            # If job has dependencies, it goes in a later stage
            dependencies = job_config['needs']
            if isinstance(dependencies, str):
                dependencies = [dependencies]
            stage_number = len(dependencies)
        else:
            # If no dependencies, it's in the first stage
            stage_number = 0

        # Add job to appropriate stage
        stage_name = f"Stage {stage_number}"
        if stage_name not in stages_dict:
            stages_dict[stage_name] = []

        # Add job details to the stage
        job_details = {
            'name': job_name,
            'config': job_config,
            'dependencies': job_config.get('needs', []),
        }
        stages_dict[stage_name].append(job_details)

    return stages_dict


def get_artifact_info(steps: List[dict]) -> List[dict]:
    """Extract artifact upload information from job steps"""
    artifacts = []
    for step in steps:
        if 'uses' in step and 'upload-artifact' in step.get('uses', ''):
            artifact = {
                'name': step.get('with', {}).get('name', 'unnamed'),
                'path': step.get('with', {}).get('path', 'unknown')
            }
            artifacts.append(artifact)
    return artifacts


def display_dry_run_plan(stages_dict: Dict[str, List[dict]]):
    """Display the pipeline execution plan in a clear, organized format"""
    click.echo("\nPipeline Execution Plan")
    click.echo("=====================\n")

    # Display each stage and its jobs
    for stage_name, jobs in sorted(stages_dict.items()):
        click.echo(f"{stage_name}:")
        click.echo("-" * 50)

        for job in jobs:
            job_name = job['name']
            job_config = job['config']

            # Display job name and its dependencies
            click.echo(f"\nJob: {job_name}")
            if job['dependencies']:
                deps = job['dependencies']
                if isinstance(deps, str):
                    deps = [deps]
                click.echo(f"Dependencies: {', '.join(deps)}")

            # Display execution environment
            click.echo(
                f"Runs on: {job_config.get('runs-on', 'not specified')}")

            # Display steps/commands
            if 'steps' in job_config:
                click.echo("\nSteps:")
                for step in job_config['steps']:
                    # Display step name
                    if 'name' in step:
                        click.echo(f"  • {step['name']}")

                    # Display commands if present
                    if 'run' in step:
                        for line in step['run'].split('\n'):
                            if line.strip():
                                click.echo(f"    $ {line.strip()}")

                # Display artifact information
                artifacts = get_artifact_info(job_config['steps'])
                if artifacts:
                    click.echo("\nArtifacts to be uploaded:")
                    for artifact in artifacts:
                        click.echo(
                            f"  • {artifact['name']}: {artifact['path']}")

            click.echo("")


def start_dry_run(config_file: str):
    """
    Main function to perform the dry run.
    Loads configuration and displays execution plan.
    """
    # Set default config file if customer not specified
    if config_file == 'default':
        config_file = 'config.yml'

    # Find the configuration file
    config_path = find_config_file(config_file)

    # Load configuration
    config = load_yaml_file(config_path)
    if not config:
        return

    # Check for jobs section
    if 'jobs' not in config:
        click.echo("Error: No jobs section found in configuration")
        return

    # Get jobs organized by stages
    stages_dict = get_jobs_by_stage(config)

    # Display the execution plan
    display_dry_run_plan(stages_dict)

from urllib.parse import quote

import click
import requests
import json
import sys
import logging
from datetime import datetime
from typing import Tuple, Optional
from cli.commands import check_config
from cli.commands.cancel_pipeline import cancel_pipeline
from cli.commands.dryrun import start_dry_run
from cli.commands.run_pipelines.job_executor import PipelineRunner
from cli.utils.logging_config import set_logging_level, log_success, log_failure

# Database server URL
DB_SERVER_URL = "http://127.0.0.1:8000"

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """T2 CI/CD Pipeline CLI tool"""
    if ctx.invoked_subcommand is None:
        # Invoke the check command with the default configuration file
        ctx.invoke(check, config_file="pipelines.yml")


@cli.command(help="Validate the configuration file")
@click.option(
    "--config-file",
    default="pipelines.yml",
    help="The local configuration file that you'd like to validate.",
)
def check(config_file):
    """T2 CI/CD Pipeline CLI tool"""
    check_config.start_check_config(config_file)


@cli.command(help="Perform a dry run of the pipeline")
@click.argument("config", default="config.yml")
def dry_run(config):
    """Perform a dry run of the pipeline"""
    if config == "config.yml":
        click.echo("Performing dry run using default configuration")
    else:
        click.echo(f"Performing dry run using configuration: {config}")
    start_dry_run(config)


"""
Register the run_pipeline as a CLI command.
"""


@click.command(name="run", help="Run a CI/CD pipeline.")
@click.option("--local", is_flag=True, required=True, help="Run pipeline locally")
@click.option(
    "--repo",
    help="Repository path or URL. Defaults to current directory if not provided",
)
@click.option("--branch", default="main", help="Branch name")
@click.option("--commit", default="latest", help="Commit hash or 'latest'")
@click.option("--pipeline", help="Pipeline name matching 'name' field in YAML")
@click.option("--file", help="Path to config file (absolute/relative/name)")
@click.option(
    "--override",
    multiple=True,
    help="Override config values (key=value), can be used multiple times",
)
@click.option("--verbose", "-v", is_flag=True, help="Show warnings and errors")
@click.option("--vv", is_flag=True, help="Show additional debug information")
def run_pipeline(
    local: bool,
    repo: str,
    branch: str,
    commit: str,
    pipeline: str,
    file: str,
    override: Tuple[str],
    verbose: bool,
    vv: bool,
) -> None:
    """
    Run a CI/CD pipeline locally or with Docker.

    The pipeline can be specified either by name (--pipeline) or file path (--file).
    If neither is provided, all pipelines in the .cicd-pipelines directory will be executed.

    Repository can be:
    1. Remote URL (HTTPS only): --repo https://github.com/user/repo
    2. Local path: --repo /path/to/repo
    3. Current directory: (no --repo option)

    Output Detail Levels:
    - Default: Only shows pipeline success/failure status
    - --verbose (-v): Shows warnings and errors
    - --vv: Shows additional debug information

    Examples:
        # Run specific pipeline from current directory
        xx run --local --pipeline "Test Pipeline"

        # Run with verbose output
        xx run --local -v --pipeline "Test Pipeline"

        # Run with debug output
        xx run --local --vv --pipeline "Test Pipeline"

        # Run from remote repository
        xx run --local --repo https://github.com/user/repo --pipeline ci

        # Run specific config file with overrides
        xx run --local --file ci.yml --override "global.docker.image=gradle:jdk8"

        # Run with multiple overrides
        xx run --local --override "global.registry=docker.io" --override "global.image=ubuntu:20.04"

        # Run specific branch and commit
        xx run --local --repo ./my-repo --branch feature --commit abc123 --pipeline test
    """
    execution_success = False

    try:
        # Set up logging based on verbosity flags
        set_logging_level(verbose, vv)

        if pipeline and file:
            raise click.UsageError("Cannot specify both --pipeline and --file")

        # Create Runner
        runner = PipelineRunner()

        # Log configuration details (only in debug mode)
        logger.debug("Pipeline configuration:")
        config_details = {
            "Repository": repo or "Current directory",
            "Branch": branch,
            "Commit": commit,
            "Pipeline": pipeline or "All pipelines",
            "Config file": file,
            "Overrides": override or "None",
            "Mode": "Local" if local else "Docker",
            "Verbosity": "Debug" if vv else "Verbose" if verbose else "Default",
        }
        for key, value in config_details.items():
            logger.debug(f"  {key}: {value}")

        # Basic pipeline start notification (shown in all modes)
        logger.info("Starting pipeline execution")

        # Prepare and execute pipeline
        pipeline_config = runner.prepare_pipeline(
            repo=repo,
            branch=branch,
            commit=commit,
            pipeline=pipeline,
            config_file=file,
            overrides=list(override) if override else None,
            local=local,
        )

        runner.execute_pipeline(pipeline_config)

        # If we reach here, execution was successful
        execution_success = True

    except click.UsageError as e:
        # CLI usage errors (shown in all modes)
        log_failure(f"Invalid usage: {str(e)}")
        sys.exit(1)

    except click.Abort:
        # Handle keyboard interrupts or explicit aborts
        log_failure("Pipeline execution aborted by user")
        sys.exit(1)

    except Exception as e:
        # Unexpected errors
        log_failure(f"Pipeline execution failed: {str(e)}")
        if vv:  # Show traceback only in debug mode
            logger.debug("Detailed error information:", exc_info=True)
        sys.exit(1)

    finally:
        # Show final execution status (shown in all modes)
        if execution_success:
            log_success("Pipeline execution completed successfully")
            sys.exit(0)
        else:
            log_failure("Pipeline execution failed")
            sys.exit(1)


# Register the `run_pipeline` command explicitly
cli.add_command(run_pipeline)


# Database Commands
@cli.group(name="db")
def db_commands():
    """Database operations for the CI/CD pipeline"""
    pass


# Repository Commands
@db_commands.group(name="repo")
def repo_commands():
    """Repository-related database operations"""
    pass


@repo_commands.command(name="create")
@click.argument("repo_url")
@click.option("--local", is_flag=True, help="Whether the repository is local")
def create_repo(repo_url: str, local: bool):
    """Create a new repository entry"""
    try:
        # URL encode the repository URL to handle special characters
        encoded_repo_url = quote(repo_url, safe="")

        # Use query parameters instead of path parameters for the boolean
        response = requests.post(
            f"{DB_SERVER_URL}/repo/post",
            params={"repo_url": encoded_repo_url, "is_local": local},
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@repo_commands.command(name="get")
@click.argument("repo_id", type=int)
def get_repo_info(repo_id: int):
    """Get repository information"""
    try:
        response = requests.get(f"{DB_SERVER_URL}/repo/get/{repo_id}")
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Pipeline Commands
@db_commands.group(name="pipeline")
def pipeline_commands():
    """Pipeline-related database operations"""
    pass


@pipeline_commands.command(name="create")
@click.argument("repo_id", type=int)
@click.argument("pipeline_name")
def create_pipeline(repo_id: int, pipeline_name: str):
    """Create a new pipeline"""
    try:
        response = requests.post(
            f"{DB_SERVER_URL}/pipeline/post/{repo_id}/{pipeline_name}"
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@pipeline_commands.command(name="get")
@click.argument("pipeline_id", type=int)
def get_pipeline_info(pipeline_id: int):
    """Get pipeline information"""
    try:
        response = requests.get(f"{DB_SERVER_URL}/pipeline/get/{pipeline_id}")
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Pipeline Run Commands
@db_commands.group(name="run")
def pipeline_run_commands():
    """Pipeline run-related database operations"""
    pass


@pipeline_run_commands.command(name="create")
@click.argument("status", type=int)
@click.argument("pipeline_id", type=int)
@click.argument("git_commit_hash")
@click.argument("run_number", type=int)
@click.option(
    "--start-time", default=datetime.now().isoformat(), help="Start time in ISO format"
)
@click.option(
    "--end-time", default=datetime.now().isoformat(), help="End time in ISO format"
)
def create_pipeline_run(
    status: int,
    pipeline_id: int,
    git_commit_hash: str,
    run_number: int,
    start_time: str,
    end_time: str,
):
    """Create a new pipeline run"""
    try:
        response = requests.post(
            f"{DB_SERVER_URL}/pipeline_run/post/{status}/{pipeline_id}/{git_commit_hash}/"
            f"{run_number}/{start_time}/{end_time}"
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@pipeline_run_commands.command(name="get")
@click.argument("pipeline_run_id", type=int)
def get_pipeline_run(pipeline_run_id: int):
    """Get pipeline run information"""
    try:
        response = requests.get(f"{DB_SERVER_URL}/pipeline_run/get/{pipeline_run_id}")
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Stage Commands
@db_commands.group(name="stage")
def stage_commands():
    """Stage-related database operations"""
    pass


@stage_commands.command(name="create")
@click.argument("pipeline_run_id", type=int)
@click.argument("status", type=int)
@click.argument("run_number", type=int)
@click.option(
    "--start-time", default=datetime.now().isoformat(), help="Start time in ISO format"
)
@click.option(
    "--end-time", default=datetime.now().isoformat(), help="End time in ISO format"
)
@click.option("--stage-name", help="Optional stage name")
def create_stage(
    pipeline_run_id: int,
    status: int,
    run_number: int,
    start_time: str,
    end_time: str,
    stage_name: Optional[str] = None,
):
    """Create a new stage. Required arguments are pipeline_run_id, status, and run_number."""
    try:
        response = requests.post(
            f"{DB_SERVER_URL}/stage/post/{pipeline_run_id}/{status}/{run_number}/{start_time}/{end_time}",
            params={"stage_name": stage_name} if stage_name else None,
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@stage_commands.command(name="get")
@click.argument("stage_id", type=int)
def get_stage(stage_id: int):
    """Get stage information"""
    try:
        response = requests.get(f"{DB_SERVER_URL}/stage/get/{stage_id}")
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Job Commands
@db_commands.group(name="job")
def job_commands():
    """Job-related database operations"""
    pass


@job_commands.command(name="create")
@click.argument("stage_id", type=int)
@click.argument("status", type=int)
@click.argument("run_number", type=int)
@click.option("--allow-failure", is_flag=True, help="Whether job failure is allowed")
@click.option(
    "--start-time", default=datetime.now().isoformat(), help="Start time in ISO format"
)
@click.option(
    "--end-time", default=datetime.now().isoformat(), help="End time in ISO format"
)
def create_job(
    stage_id: int,
    status: int,
    run_number: int,
    allow_failure: bool,
    start_time: str,
    end_time: str,
):
    """Create a new job"""
    try:
        response = requests.post(
            f"{DB_SERVER_URL}/job/post/{stage_id}/{status}/{allow_failure}/{run_number}/{start_time}/{end_time}"
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@job_commands.command(name="get")
@click.argument("job_id", type=int)
def get_job(job_id: int):
    """Get job information"""
    try:
        response = requests.get(f"{DB_SERVER_URL}/job/get/{job_id}")
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Report Commands
@cli.group(name="report")
def report_commands():
    """Reporting commands for the pipeline"""
    pass


@report_commands.command(name="list")
@click.option("--repo", required=True, help="Repository URL or path")
@click.option("--local", is_flag=True, help="Is local repository")
@click.option("--pipeline", help="Filter by pipeline name")
@click.option("--run", type=int, help="Filter by run number")
@click.option("--stage", type=int, help="Filter by stage ID")
@click.option("--job", type=int, help="Filter by job ID")
def list_reports(
    repo: str,
    local: bool,
    pipeline: Optional[str] = None,
    run: Optional[int] = None,
    stage: Optional[int] = None,
    job: Optional[int] = None,
):
    """List pipeline reports"""
    try:
        response = requests.get(
            f"{DB_SERVER_URL}/report",
            params={
                "repo": repo,
                "local": local,
                "pipeline": pipeline,
                "run": run,
                "stage": stage,
                "job": job,
            },
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@report_commands.command(name="summary")
@click.argument("pipeline_name")
@click.argument("run_number", type=int)
def pipeline_summary(pipeline_name: str, run_number: int):
    """Get pipeline run summary"""
    try:
        response = requests.get(
            f"{DB_SERVER_URL}/pipeline/{pipeline_name}/run/{run_number}/summary"
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@report_commands.command(name="stage")
@click.argument("pipeline_name")
@click.argument("run_number", type=int)
@click.option("--id", "stage_id", type=int, help="Stage ID")
@click.option("--name", "stage_name", help="Stage name")
def stage_summary(
    pipeline_name: str,
    run_number: int,
    stage_id: Optional[int] = None,
    stage_name: str = None,
):
    """Get stage summary. Either stage ID or stage name must be provided.

    Examples:
        t2-cicd report stage "T2 pipeline" 1 --id 1
        t2-cicd report stage "T2 pipeline" 1 --name build-stage
    """
    if stage_id is None and stage_name is None:
        click.echo(
            "Error: Either stage ID (--id) or stage name (--name) must be provided"
        )
        return

    try:
        params = {}
        if stage_id is not None:
            params["stage_id"] = stage_id
        if stage_name is not None:
            params["stage_name"] = stage_name

        response = requests.get(
            # Updated URL
            f"{DB_SERVER_URL}/pipeline/{pipeline_name}/run/{run_number}/stage-summary",
            params=params,
        )

        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


@report_commands.command(name="job")
@click.argument("pipeline_name")
@click.argument("run_number", type=int)
@click.argument("job_id", type=int)
@click.option("--id", "stage_id", type=int, help="Stage ID")
@click.option("--name", "stage_name", help="Stage name")
def job_summary(
    pipeline_name: str,
    run_number: int,
    job_id: int,
    stage_id: int = None,
    stage_name: str = None,
):
    """Get job summary

    Examples:
        t2-cicd report job my-pipeline 123 456 --id 1
        t2-cicd report job my-pipeline 123 456 --name build-stage
        t2-cicd report job my-pipeline 123 456 --id 1 --name build-stage
    """
    if stage_id is None and stage_name is None:
        click.echo(
            "Error: Either stage ID (--id) or stage name (--name) must be provided"
        )
        return

    try:
        response = requests.get(
            f"{DB_SERVER_URL}/pipeline/{pipeline_name}/run/{run_number}/stage/job/{job_id}/summary",
            params={"stage_id": stage_id, "stage_name": stage_name},
        )
        if response.status_code == 200:
            click.echo(json.dumps(response.json(), indent=2))
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Status Command
@cli.command(name="status", help="Check the status of running pipelines.")
@click.option("--repo", help="Repository URL or path to filter by")
@click.option("--pipeline", help="Pipeline name to filter by")
@click.option(
    "--days", type=int, default=7, help="Number of days to look back (default: 7)"
)
def check_status(repo: Optional[str], pipeline: Optional[str], days: int):
    """Check the status of running pipelines"""
    try:
        params = {"days": days}
        if repo:
            params["repo"] = repo
        if pipeline:
            params["pipeline"] = pipeline

        response = requests.get(f"{DB_SERVER_URL}/status", params=params)

        if response.status_code == 200:
            statuses = response.json()
            if not statuses:
                click.echo("No pipeline runs found for the specified criteria.")
                return

            for status in statuses:
                click.echo("=" * 50)
                click.echo(f"Pipeline: {status['pipeline_name']}")
                click.echo(f"Run #{status['run_number']}")
                click.echo(f"Status: {status['status']}")
                click.echo(f"Started: {status['start_time']}")
                if status["completion_time"]:
                    click.echo(f"Completed: {status['completion_time']}")
                if status["stages"]:
                    click.echo("\nStages:")
                    for stage in status["stages"]:
                        click.echo(f"  - {stage['name']}: {stage['status']}")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        click.echo(f"Failed to connect to server: {e}")


# Help command
@cli.command(name="help", help="Show help information for commands")
@click.argument("command_name", required=False)
def show_help(command_name: Optional[str]):
    """Show detailed help information for commands"""
    if not command_name:
        ctx = click.get_current_context()
        click.echo(cli.get_help(ctx))
        return

    # Get the command object
    cmd = cli.get_command(None, command_name)
    if not cmd:
        click.echo(f"No such command: {command_name}")
        return

    # Show help for the specific command
    ctx = click.Context(cmd, info_name=command_name)
    click.echo(cmd.get_help(ctx))


# Cancel Command
@cli.command(name='cancel', help="Cancel a running pipeline.")
@click.argument('pipeline_name')
@click.argument('git_commit_hash')
@click.argument('run_number', type=int)
def cancel_command(pipeline_name: str, git_commit_hash: str, run_number: int):
    """
    Cancel a running pipeline by pipeline name, git commit hash, and run number.
    """
    try:
        cancel_pipeline(pipeline_name, git_commit_hash, run_number, timestamp=datetime.now())
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


def main():
    """Main entry point for the CLI"""
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


# Register all commands
cli.add_command(run_pipeline)

if __name__ == "__main__":
    main()

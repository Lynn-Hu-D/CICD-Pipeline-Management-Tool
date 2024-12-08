import os
import yaml
import click

from cli.commands.run_pipelines.pipeline_validation import PipelineValidator


def start_check_config(config_file):
    """
    Check the configuration file for validity, defaulting to
    .cicd-pipelines/pipelines.yml if no arguments are provided.
    """
    config_file = os.path.join('.cicd-pipelines', config_file)
    # Check if the configuration file exists
    if config_file and not os.path.exists(config_file):
        click.echo(f"Error: Configuration file '{config_file}' not found.")
        return

    # Set the default config file if none is provided
    if not config_file:
        config_file = '.cicd-pipelines/pipelines.yml'

    # Check the file extension and validate accordingly
    _, file_extension = os.path.splitext(config_file)

    try:
        if file_extension.lower() == '.yml' or file_extension.lower() == '.yaml':
            """Read configuration from one or multiple YAML files in a local repository."""
            validator = PipelineValidator()
            config = []
            repo_path = os.getcwd()
            file = os.path.join(repo_path, config_file)
            data = validator.load_yaml(file)
            config.append({file: data})
            if validator.validate_pipelines(config):
                click.echo(f"Configuration file '{config_file}' is valid.")
            else:
                click.echo(
                    f"Configuration file '{config_file}' is not valid, check the validation report.")
        else:
            click.echo(
                "Unsupported file format. Please use a .yml, .yaml, or .json file.")
    except (yaml.YAMLError) as e:
        click.echo(f"Error in configuration file '{config_file}': {e}")

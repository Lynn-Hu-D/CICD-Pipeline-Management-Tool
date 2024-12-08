import re
from collections import defaultdict
import ruamel.yaml
import logging
from ruamel.yaml.constructor import DuplicateKeyError

# Configure logging
logger = logging.getLogger(__name__)


class PipelineValidator:
    """
    A class to validate CI/CD pipeline YAML configuration files.

    This class provides functionalities to load a pipeline YAML file, validate
    the uniqueness of job names, detect cyclic dependencies among jobs, and
    generate a detailed validation report.

    Attributes:
        _error_messages (list): A list to store error messages encountered during validation.
    """

    def __init__(self):
        self._error_messages = []

    def load_yaml(self, file_path):
        """
        Loads a YAML file and parses its content.

        Utilizes ruamel.yaml to parse the YAML file, handling various exceptions
        such as duplicate keys, syntax errors, and file not found errors. Errors
        encountered during loading are logged and re-raised to halt execution.

        Args:
            file_path (str): The path to the YAML file to be loaded.

        Returns:
            dict or list: The parsed YAML content with location information for each node.

        Raises:
            DuplicateKeyError: If the YAML file contains duplicate keys.
            ruamel.yaml.YAMLError: If there is a syntax error in the YAML file.
            FileNotFoundError: If the specified file does not exist.
            Exception: For any other unexpected errors during YAML loading.
        """
        logger.debug(f"Loading YAML file: {file_path}")  # Debug level

        yaml = ruamel.yaml.YAML()
        try:
            with open(file_path, "r") as file:
                pipeline_data = yaml.load(file)
                # Add the file path to each node's location data
                for job_name, job_details in pipeline_data.get("jobs", {}).items():
                    if hasattr(job_details, "lc"):
                        # Associate the file path with the location data
                        job_details.lc.file_path = file_path
                logger.debug(
                    f"Successfully loaded YAML file: {file_path}"
                )  # Debug level
                return pipeline_data
        except DuplicateKeyError as e:
            # Create a custom error message for DuplicateKeyError
            line = getattr(e.context_mark, "line", None) + 1
            col = getattr(e.context_mark, "column", None) + 1
            match = re.search(r'duplicate key "(.+?)"', str(e))
            duplicate_key = match.group(1) if match else "unknown"

            error_message = (
                f"Duplicate key error detected.\n"
                f"\tFound duplicate key named '{duplicate_key}'.\n"
                f"\tConsider renaming the key or restructuring the file to avoid duplication."
            )
            self._log_error(error_message, file_path=file_path, line=line, col=col)
            raise DuplicateKeyError(error_message)
        except FileNotFoundError:
            error_message = f"{file_path}: File not found."
            self._log_error(error_message, file_path=file_path)
            raise
        except Exception as e:
            error_message = f"{file_path}: Unexpected error while loading YAML. Detailed error: {str(e)}"
            self._log_error(error_message, file_path=file_path)
            raise

    def _log_error(self, message, file_path=None, line=None, col=None):
        """
        Logs an error message by printing it and storing it in the _error_messages list.
        If file_path, line, and column information is available, adds a hyperlink for easy navigation.

        Args:
            message (str): The error message to be logged.
            file_path (str, optional): The file path where the error occurred.
            line (int, optional): The line number where the error occurred.
            col (int, optional): The column number where the error occurred.
        """
        if file_path and line is not None and col is not None:
            # Format the error message as requested
            detailed_message = f"{message}"
            link = f"vscode://file/{file_path}:{line}:{col}"
            detailed_message += f"\n\t[Open in Editor]({link})"
        elif file_path:
            detailed_message = message + f"[{file_path}]"
        else:
            detailed_message = message

        logger.info(detailed_message)  # Always log errors
        self._error_messages.append(detailed_message)

    def _detect_cycle(self, file_path, jobs):
        """
        Detects cycles in job dependencies within the pipeline.

        Builds a dependency graph from the provided jobs and uses Depth-First Search (DFS)
        to detect any cycles. If a cycle is found, an error message detailing the cycle
        path and locations of involved jobs is logged.

        Args:
            jobs (dict): A dictionary representing jobs and their details from the pipeline.

        Returns:
            bool: True if a cycle is detected, False otherwise.
        """
        graph = defaultdict(list)
        job_to_location = {}

        # Build the dependency graph and store job locations
        for job_name, job_details in jobs.items():
            # Get line and column information for the job
            if hasattr(job_details, "lc"):
                line = job_details.lc.line + 1  # Lines are zero-indexed in ruamel.yaml
                col = job_details.lc.col + 1
                job_to_location[job_name] = (line, col)
            else:
                job_to_location[job_name] = None

            if "needs" in job_details:
                # Ensure needs is treated as a list of dependencies
                dependencies = job_details["needs"]
                if isinstance(dependencies, str):
                    # Convert to list if it's a single string
                    dependencies = [dependencies]

                for dep in dependencies:
                    line = None
                    col = None
                    if dep in jobs:
                        graph[job_name].append(dep)
                    else:
                        loc = job_to_location[job_name]
                        if loc:
                            line = loc[0]
                            col = loc[1]
                            error_message = f"{job_name}: Job '{dep}' not found (dependency of '{job_name}')"
                        else:
                            error_message = f"{job_name}: Job '{dep}' not found (dependency of '{job_name}')"
                        self._log_error(file_path, error_message, line, col)

        # Helper function for DFS cycle detection
        def _dfs(node, visited, on_path, path):
            """
            Performs Depth-First Search (DFS) to detect cycles starting from the given node.

            Args:
                node (str): The current job being visited.
                visited (set): A set of jobs that have been visited.
                on_path (set): A set of jobs that are on the current DFS path.
                path (list): A list representing the current DFS path.

            Returns:
                bool: True if a cycle is detected, False otherwise.
            """
            visited.add(node)
            on_path.add(node)
            path.append(node)

            for neighbor in graph[node]:
                if neighbor not in visited:
                    if _dfs(neighbor, visited, on_path, path):
                        return True
                elif neighbor in on_path:
                    # Cycle detected
                    cycle_start_index = path.index(neighbor)
                    cycle_path = path[cycle_start_index:] + [neighbor]
                    # Build the cycle path with line and column info
                    line = None
                    col = None
                    cycle_info = []
                    for job in cycle_path:
                        loc = job_to_location.get(job)
                        if loc:
                            line = loc[0] + 1
                            col = loc[1] + 1
                            cycle_info.append(f"{job}(line {line}, column {col})")
                        else:
                            cycle_info.append(f"{job}(unknown location)")
                    cycle_str = " -> ".join(cycle_info)
                    # Also include the line and column of the job where the cycle was detectedP
                    loc = job_to_location.get(neighbor)
                    if loc:
                        line = loc[0] + 1
                        col = loc[1] + 1
                        error_message = f"Cycle detected at job '{neighbor}' (line {line}, column {col})"
                    else:
                        error_message = f"Cycle detected at job '{neighbor}'"
                    self._log_error(
                        f"{error_message}. Cycle path: {cycle_str}",
                        file_path,
                        line,
                        col,
                    )
                    return True

            on_path.remove(node)
            path.pop()
            return False

        visited = set()
        for job_name in jobs:
            if job_name not in visited:
                if _dfs(job_name, visited, set(), []):
                    return True
        return False

    def _validate_unique_stages(self, file_path, pipeline_data):
        """
        Validates the uniqueness of stage names and order values in the pipeline.

        Checks for duplicate stage names and duplicate order numbers. Logs errors for
        any duplicates found.

        Args:
            pipeline_data (dict): The parsed pipeline YAML data.

        Returns:
            bool: True if all stage names and orders are unique, False otherwise.
        """
        stages = pipeline_data.get("stages", [])

        stage_names = {}
        is_valid = True
        error_line = None
        error_col = None

        for stage in stages:
            name = stage.get("name")

            # Validate unique stage names
            if name in stage_names:
                loc = getattr(stage, "lc", None)
                if loc and hasattr(loc, "line") and hasattr(loc, "col"):
                    error_line = loc.line + 1
                    error_col = loc.col + 1
                    error_message = f"{name}: Duplicate stage name '{name}' found"
                else:
                    error_message = f"{name}: Duplicate stage name '{name}' found"
                self._log_error(error_message, file_path, error_line, error_col)
                is_valid = False
            else:
                stage_names[name] = True

        return is_valid

    def _validate_unique_jobs(self, file_path, pipeline_data):
        """
        Validates the uniqueness of job names in the pipeline.

        Checks for duplicate job names and logs an error if any duplicates are found.

        Args:
            pipeline_data (dict): The parsed pipeline YAML data.

        Returns:
            bool: True if all job names are unique, False otherwise.
        """
        jobs = pipeline_data.get("jobs", {})
        line = None
        col = None
        job_names = {}
        # Check for duplicate job names
        for job_name, job_details in jobs.items():
            if job_name in job_names:
                if hasattr(job_details, "lc"):
                    line = job_details.lc.line + 1
                    col = job_details.lc.col + 1
                    error_message = f"{job_name}: Duplicate job name '{job_name}' found"
                else:
                    error_message = f"{job_name}: Duplicate job name '{job_name}' found"
                self._log_error(error_message, file_path, line, col)
                return False
            job_names[job_name] = True

        return True

    # Save error messages to the validation report
    def save_error_report(self, report_path):
        """
        Saves all logged error messages to a specified report file.

        Writes each error message to the given file path, with each message on a new line.

        Args:
            report_path (str): The file path where the validation report will be saved.
        """
        logger.debug(f"Saving error report to: {report_path}")  # Debug level
        with open(report_path, "w") as f:
            for message in self._error_messages:
                f.write(message + "\n")
        logger.debug("Error report saved successfully")  # Debug level

    def _validate_unique_pipeline_names(self, pipeline_data):
        """
        Validates that all pipeline names across multiple pipeline files are unique.

        Args:
            pipeline_data (list): A list of dictionaries where each dictionary contains
            a file path as the key and the pipeline data as the value.

        Returns:
            bool: True if all pipeline names are unique, False otherwise.
        """
        logger.debug("Checking pipeline name uniqueness...")  # Debug level
        pipeline_names = {}

        for item in pipeline_data:
            for file_path, data in item.items():
                # Ensure the pipeline has a 'name' field
                pipeline_name = data.get("name")
                if not pipeline_name:
                    error_message = (
                        f"{file_path}: Pipeline does not have a 'name' field."
                    )
                    self._log_error(error_message, file_path=file_path)
                    logger.debug("Checking pipeline name uniqueness...")  # Debug level
                    return False

                # Check for duplicate pipeline names
                if pipeline_name in pipeline_names:
                    existing_file = pipeline_names[pipeline_name]
                    error_message = (
                        f"Duplicate pipeline name '{pipeline_name}' found in:\n"
                        f"  - {existing_file}\n"
                        f"  - {file_path}"
                    )
                    self._log_error(error_message, file_path=file_path)
                    logger.error(error_message)
                    return False
                else:
                    pipeline_names[pipeline_name] = file_path

        logger.debug("All pipeline names are unique.")
        return True

    def _validate_pipeline(self, file_path, pipeline_data):
        """
        Validates the pipeline configuration for uniqueness and cyclic dependencies.

        Performs the following validations:
            1. Ensures that all job names are unique.
            2. Detects any cyclic dependencies among jobs.

        Logs detailed error messages for any validation failures and generates a
        validation report.

        Args:
            pipeline_data (dict): The parsed pipeline YAML data.

        Returns:
            bool: True if the pipeline passes all validations, False otherwise.
        """

        logger.debug(f"Starting detailed validation for {file_path}")  # Debug level

        # Validate uniqueness of job/stage names
        logger.info("Validating uniqueness of job names...")  # Info level
        if not self._validate_unique_jobs(
            file_path, pipeline_data
        ) or not self._validate_unique_stages(file_path, pipeline_data):
            logger.error("Uniqueness validation failed. Exiting validation.")
            self.save_error_report("./validation_report.txt")
            return False

        logger.debug("Stage and job names are unique.")  # Debug level

        # Check for cycle dependencies
        logger.info("Checking for cycles in job dependencies...")  # Info level
        if self._detect_cycle(file_path, pipeline_data.get("jobs", {})):
            logger.error("Cycle detection failed. Exiting validation.")
            self.save_error_report("./validation_report.txt")
            return False

        logger.debug("No cycles detected in job dependencies.")  # Debug level
        self._log_error("Pipeline validation passed successfully.")  # Info level
        return True

    # Main validation function with detailed reporting
    def validate_pipelines(self, pipeline_data):
        """
        Validate multiple pipelines based on the provided list of dictionaries.

        Args:
        pipeline_data (list): A list of dictionaries where each dictionary contains
        a file path as the key and the pipeline data as the value.

        Returns:
            bool: True if all pipelines pass validation, False otherwise.
        """
        logger.debug("Starting pipeline validation...")

        if not self._validate_unique_pipeline_names(pipeline_data):
            logger.info("Validating pipeline names uniqueness...")  # Info level
            self.save_error_report("./validation_report.txt")
            return False

        for item in pipeline_data:
            # Since each item is a dictionary with a single key-value pair (file_path: data)
            for file_path, data in item.items():
                logger.info(f"Validating pipeline for: {file_path}")  # Info level
                if not self._validate_pipeline(file_path, data):
                    self.save_error_report("./validation_report.txt")
                    return False

        self.save_error_report("./validation_report.txt")
        return True

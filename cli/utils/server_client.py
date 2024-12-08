import datetime
from typing import Optional

import requests
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Replace with actual server URL now is only local
SERVER_URL = "http://127.0.0.1:8000"


def create_repo(repo_url: str, is_local: bool) -> int:
    """Create a new repository entry and return its ID."""
    encoded_repo_url = quote(repo_url, safe="")
    try:
        response = requests.post(
            f"{SERVER_URL}/repo/post",
            params={"repo_url": encoded_repo_url, "is_local": is_local},
        )
        if 200 <= response.status_code < 300:
            repo_info = response.json()
            repo_id = repo_info["new_repo"]["repo_id"]
            logger.info(f"Repository created with ID {repo_id}")
            logger.debug(f"Repository details: {repo_info}")
            return repo_id
        else:
            error_msg = (
                f"Failed to create repository. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def create_pipeline(repo_id: int, pipeline_name: str) -> int:
    """Create a new pipeline entry and return its ID."""
    api_url = f"{SERVER_URL}/pipeline/post/{repo_id}/{pipeline_name}"
    try:
        response = requests.post(api_url)
        if 200 <= response.status_code < 300:
            pipeline_info = response.json()
            pipeline_id = pipeline_info["new_pipeline"]["pipeline_id"]
            logger.info(f"Pipeline '{pipeline_name}' created with ID {pipeline_id}")
            logger.debug(f"Pipeline details: {pipeline_info}")
            return pipeline_id
        else:
            error_msg = (
                f"Failed to create pipeline. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def create_pipeline_run(
    status: int,
    pipeline_id: int,
    git_commit_hash: str,
    run_number: int,
    start_time: str,
    end_time: str
) -> int:
    """Create a new pipeline run entry and return its ID."""
    api_url = (
        f"{SERVER_URL}/pipeline_run/post/{status}/{pipeline_id}/"
        f"{git_commit_hash}/{run_number}/{start_time}/{end_time}"
    )
    try:
        response = requests.post(api_url)
        if 200 <= response.status_code < 300:
            run_info = response.json()
            pipeline_run_id = run_info["new_pipeline_run"]["pipeline_run_id"]
            logger.info(f"Pipeline run created with ID {pipeline_run_id}")
            logger.debug(f"Pipeline run details: {run_info}")
            return pipeline_run_id
        else:
            error_msg = (
                f"Failed to create pipeline run. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def create_stage(
    pipeline_run_id: int,
    status: int,
    stage_name: str,
    run_number: int,
    start_time: str,
    end_time: str
) -> int:
    """Create a new stage entry and return its ID."""
    api_url = f"{SERVER_URL}/stage/post/{pipeline_run_id}/{status}/{run_number}/{start_time}/{end_time}/{stage_name}"
    try:
        response = requests.post(api_url)
        if 200 <= response.status_code < 300:
            stage_info = response.json()
            stage_id = stage_info["new_stage"]["stage_id"]
            logger.info(f"Stage created with ID {stage_id}")
            logger.debug(f"Stage details: {stage_info}")
            return stage_id
        else:
            error_msg = (
                f"Failed to create stage. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def create_job(
    stage_id: int,
    status: int,
    allow_failure: bool,
    run_number: int,
    start_time: str,
    end_time: str
) -> int:
    """Create a new job entry and return its ID."""
    api_url = f"{SERVER_URL}/job/post/{stage_id}/{status}/{allow_failure}/{run_number}/{start_time}/{end_time}"
    try:
        response = requests.post(api_url)
        if 200 <= response.status_code < 300:
            job_info = response.json()
            # Update this line based on your actual API response structure
            job_id = job_info["new_job"]["job_id"]  # Adjust the key names based on your API response
            logger.info(f"Job created with ID {job_id}")
            logger.debug(f"Job details: {job_info}")
            return job_id
        else:
            error_msg = (
                f"Failed to create job. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def update_job(job_id: int, status: int, end_time: str):
    """Update an existing job's status and end time."""
    api_url = f"{SERVER_URL}/job/update/{job_id}/{status}/{end_time}"
    try:
        response = requests.put(api_url)
        if 200 <= response.status_code < 300:
            logger.info(f"Job ID {job_id} updated successfully")
            logger.debug(f"Updated job status: {status}, end time: {end_time}")
        else:
            error_msg = (
                f"Failed to update job. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def update_stage(stage_id: int, status: int, end_time: str):
    """Update an existing stage's status and end time."""
    api_url = f"{SERVER_URL}/stage/update/{stage_id}/{status}/{end_time}"
    try:
        response = requests.put(api_url)
        if 200 <= response.status_code < 300:
            logger.info(f"Stage ID {stage_id} updated successfully")
            logger.debug(f"Updated stage status: {status}, end time: {end_time}")
        else:
            error_msg = (
                f"Failed to update stage. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def update_pipeline_run(pipeline_run_id: int, status: int, end_time: str):
    """Update an existing pipeline run's status and end time."""
    api_url = f"{SERVER_URL}/pipeline_run/update/{pipeline_run_id}/{status}/{end_time}"
    try:
        response = requests.put(api_url)
        if 200 <= response.status_code < 300:
            logger.info(f"Pipeline run ID {pipeline_run_id} updated successfully")
            logger.debug(f"Updated pipeline run status: {status}, end time: {end_time}")
        else:
            error_msg = (
                f"Failed to update pipeline run. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def get_pipeline_run(
        pipeline_name: Optional[str] = None,
        git_commit_hash: Optional[str] = None,
        run_number: Optional[int] = None,
) -> dict:
    """
    Fetch pipeline run information by pipeline name, git commit hash, and/or run number.

    Args:
        pipeline_name (Optional[str]): The name of the pipeline.
        git_commit_hash (Optional[str]): The Git commit hash of the pipeline run.
        run_number (Optional[int]): The run number of the pipeline run.

    Returns:
        dict: The JSON response containing the pipeline run details.

    Raises:
        Exception: If the request fails or the server responds with an error.
    """
    api_url = f"{SERVER_URL}/pipeline_run/get"

    # Construct query parameters
    params = {}
    if pipeline_name:
        params['pipeline_name'] = pipeline_name
    if git_commit_hash:
        params['git_commit_hash'] = git_commit_hash
    if run_number:
        params['run_number'] = run_number

    try:
        logger.debug(
            f"Fetching pipeline run for pipeline '{pipeline_name}' at commit {git_commit_hash}"
        )
        response = requests.get(api_url, params=params)
        if 200 <= response.status_code < 300:
            pipeline_run_info = response.json()
            logger.info("Successfully retrieved pipeline run information")
            logger.debug(f"Pipeline run details: {pipeline_run_info}")
            return pipeline_run_info
        else:
            error_msg = (
                f"Failed to fetch pipeline run. "
                f"\tStatus code: {response.status_code}, "
                f"\tResponse: {response.text}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)

    except requests.exceptions.HTTPError as http_err:
        raise Exception(f"HTTP error occurred: {http_err} - Response: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(
            f"Failed to fetch pipeline run. URL: {api_url}, Error: {e}"
        )


def get_max_pipeline_run_number(
        pipeline_name: str,
        git_commit_hash: str,
) -> int:
    """
    Fetch the maximum run_number for a given pipeline_name and git_commit_hash.

    Args:
        pipeline_name (str): The name of the pipeline.
        git_commit_hash (str): The Git commit hash of the pipeline run.

    Returns:
        int: The maximum run_number.

    Raises:
        Exception: If the request fails or the server responds with an error.
    """
    api_url = f"{SERVER_URL}/pipeline_run/get_max_run_number"
    params = {
        "pipeline_name": pipeline_name,
        "git_commit_hash": git_commit_hash
    }

    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)

        data = response.json()
        max_run_number = data.get("max_run_number")

        return max_run_number

    except requests.exceptions.HTTPError as http_err:
        raise Exception(f"HTTP error occurred: {http_err} - Response: {response.text}")

    except requests.exceptions.RequestException as e:
        raise Exception(
            f"Failed to fetch maximum run_number. URL: {api_url}, Error: {e}"
        )

    except ValueError:
        raise Exception("Invalid JSON response received.")


def update_canceled_stages_and_jobs(
        pipeline_name: str,
        git_commit_hash: str,
        run_number: int,
        timestamp: datetime):
    """
    Update stages, jobs, and pipeline run ending
    after the given timestamp to 'canceled'.

    Args:
        pipeline_name (str): Name of the pipeline.
        git_commit_hash (str): Git commit hash.
        run_number (int): Run number.
        timestamp (datetime): Cancellation timestamp.

    Raises:
        Exception: If any errors occur during the update process.
    """
    try:
        # Format timestamp as ISO string
        timestamp_str = timestamp.isoformat()

        # Prepare common parameters
        common_params = {
            'pipeline_name': pipeline_name,
            'git_commit_hash': git_commit_hash,
            'run_number': run_number,
            'filter_by_end_time': 'true',
            'end_time': timestamp_str
        }

        # Retrieve stages ending after the timestamp
        stages_url = f"{SERVER_URL}/stage/get"
        stages_response = requests.get(stages_url, params=common_params)
        stages_response.raise_for_status()
        stages = stages_response.json().get('stages', [])

        # Update each stage to 'canceled'
        for stage in stages:
            stage_id = stage['stage_id']
            update_stage(stage_id, 5, timestamp_str)

        # Retrieve jobs ending after the timestamp
        jobs_url = f"{SERVER_URL}/job/get"
        jobs_response = requests.get(jobs_url, params=common_params)
        jobs_response.raise_for_status()
        jobs = jobs_response.json().get('jobs', [])

        # Update each job to 'canceled'
        for job in jobs:
            job_id = job['job_id']
            update_job(job_id, 5, timestamp_str)

        pipeline_runs = get_pipeline_run(
            pipeline_name,
            git_commit_hash,
            run_number
        )

        pipeline_run_id = pipeline_runs["pipeline_runs"][0]["pipeline_run_id"]
        # Update the pipeline run status to 'canceled'
        update_pipeline_run(pipeline_run_id,
                            5,
                            timestamp_str)

        print("Pipeline cancellation completed. "
              "Stages, jobs, and pipeline run updated to 'canceled' status.")

    except requests.exceptions.HTTPError as http_err:
        raise Exception(f"HTTP error occurred: {http_err} - "
                        f"Response: {http_err.response.text}")
    except requests.exceptions.RequestException as req_err:
        raise Exception(f"Request error occurred: {req_err}")
    except Exception as e:
        raise Exception(f"Failed to cancel pipeline: {e}")

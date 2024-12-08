import time
from datetime import datetime

from cli.utils.server_client import (
    get_pipeline_run,
    update_canceled_stages_and_jobs
)


def cancel_pipeline(pipeline_name: str,
                    git_commit_hash: str,
                    run_number: int,
                    timestamp: datetime):
    """
    Cancel a pipeline by marking stages and jobs with end times later than
    the given timestamp as 'canceled'.

    Args:
        pipeline_name (str): Name of the pipeline.
        git_commit_hash (str): Commit hash associated with the pipeline.
        run_number (int): Run number associated with the pipeline.
        timestamp (datetime): Timestamp indicating
            when the cancellation was requested.

    Raises:
        Exception: If the pipeline is already completed or other errors occur.
    """
    # Get initial pipeline status
    current_status = _get_pipeline_status(pipeline_name, git_commit_hash, run_number)
    print(f"current status is {current_status}")

    # Validate if the pipeline can be canceled
    if current_status in ('completed', 'failed', 'canceled'):
        raise Exception('The pipeline is already completed or canceled '
                        'and cannot be canceled.')

    # Poll until the pipeline finishes
    while current_status == 'running':
        print("Pipeline is still running... Waiting before rechecking.")
        time.sleep(5)
        current_status = _get_pipeline_status(pipeline_name, git_commit_hash, run_number)

    if current_status in ('completed', 'failed'):
        print("Found target pipeline. Processing cancellation.")
        update_canceled_stages_and_jobs(
            pipeline_name,
            git_commit_hash,
            run_number,
            timestamp
        )

    else:
        print(f"Pipeline status: {current_status}. "
              "No further action required.")


def _get_pipeline_status(pipeline_name: str, git_commit_hash: str, run_number: int):
    """
    Get the current status of the pipeline.

    Args:
        pipeline_name (str): Name of the pipeline.
        git_commit_hash (str): Commit hash associated with the pipeline.

    Returns:
        str: Current pipeline status.
    """
    pipeline_run_response = get_pipeline_run(pipeline_name, git_commit_hash, run_number)["pipeline_runs"][0]
    status_map = {
        1: 'pending',
        2: 'running',
        3: 'completed',
        4: 'failed',
        5: 'canceled'
    }

    current_status = status_map.get(pipeline_run_response["status"], 'unknown')
    return current_status

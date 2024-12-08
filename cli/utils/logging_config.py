import logging

# Configure logging with a formatter that includes timestamp
logging.basicConfig(
    level=logging.ERROR,  # Default level
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def set_logging_level(verbose: bool = False, vv: bool = False) -> None:
    """Set logging level based on verbosity flags.

    Args:
        verbose (bool): If True, show warnings and errors
        vv (bool): If True, show additional debug info

    Default (no flags): Only shows pipeline success/failure
    --verbose: Shows warnings and errors
    --vv: Shows all debug info
    """
    logger = logging.getLogger()  # Get root logger
    if vv:
        logger.setLevel(logging.DEBUG)  # Most detailed output
    elif verbose:
        logger.setLevel(logging.INFO)  # General info, warnings, and errors
    else:
        logger.setLevel(logging.ERROR)  # Only success/failure messages


def log_success(message: str) -> None:
    """Log success messages regardless of logging level."""
    print(f"SUCCESS: {message}")


def log_failure(message: str) -> None:
    """Log failure messages regardless of logging level."""
    print(f"FAILURE: {message}")

import logging
from pathlib import Path

def setup_logging(log_file_name="ceds_ontology.log"):
    """Set up logging configuration."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter('[%(asctime)s] [%(levelname)-8s]: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    log_file = Path.cwd() / log_file_name
    try:
        file_handler = logging.FileHandler(log_file, 'w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(console_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"Failed to configure file logging: {e}")

    return logger

def destroy_logger():
    """Clean up all handlers from the logger."""
    logger = logging.getLogger(__name__)
    while logger.hasHandlers():
        handler = logger.handlers[0] if logger.handlers else None
        if handler:
            handler.close()
            logger.removeHandler(handler)

import logging
from pathlib import Path

def setup_logging(log_file_name="ceds_ontology.log"):
    """Set up logging configuration."""
    logger = logging.getLogger(__name__)
    if logger.hasHandlers():
        return logger  # Avoid re-adding handlers

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)-8s]: %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(Path.cwd() / log_file_name, 'w')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"Failed to configure file logging: {e}")

    return logger

def destroy_logger():
    """Clean up all handlers from the logger."""
    logger = logging.getLogger(__name__)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

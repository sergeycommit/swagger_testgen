"""
Helper utilities for the generator package.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def setup_logging(log_file: str = "test_case_generation.log", level: int = logging.INFO):
    """
    Configure logging for both console and file output.

    Args:
        log_file: Destination path for the log file.
        level: Logging verbosity level.
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ],
        force=True
    )


def validate_test_case(test_case: Any) -> bool:
    """
    Validate a TestCase instance before exporting.

    Args:
        test_case: TestCase-like object to validate.

    Returns:
        True if the test case passes basic validation.
    """
    required_fields = ['title', 'test_steps', 'test_type', 'api_path', 'http_method']
    
    for field in required_fields:
        if not hasattr(test_case, field):
            logger.warning(f"Test case is missing a required field: {field}")
            return False
        
        value = getattr(test_case, field)
        if not value:
            logger.warning(f"Field {field} is empty in test case: {test_case.title}")
            return False
    
    # Ensure there is at least one step
    if not test_case.test_steps or len(test_case.test_steps) == 0:
        logger.warning(f"Test case contains no steps: {test_case.title}")
        return False
    
    return True


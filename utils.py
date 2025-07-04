import os
import logging
from logging.handlers import RotatingFileHandler
import sys

def setup_logger(name="gps_reviewer", level=logging.INFO):
    """
    Set up and configure a logger for the Picture GPS Reviewer application.
    
    Args:
        name (str): Name of the logger
        level: Logging level (default: logging.INFO)
        
    Returns:
        logger: Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Don't add handlers if they already exist
    if logger.handlers:
        return logger
        
    # Create log directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'log')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'picture_gps_reviewer.log')
    
    # Create file handler for logging to a file
    file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5)  # 10MB max size, keep 5 backups
    file_handler.setLevel(level)
    
    # Create console handler for logging to the console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Create a formatter and set it for both handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def get_csv_path(filename, ensure_csv_dir=True):
    """
    Get the path to a CSV file in the data/csv directory
    
    Args:
        filename (str): Name or path of the CSV file
        ensure_csv_dir (bool): Whether to ensure the CSV directory exists
        
    Returns:
        str: Absolute path to the CSV file in the data/csv directory
    """
    csv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'csv')
    if ensure_csv_dir:
        os.makedirs(csv_dir, exist_ok=True)
    
    # If filename is not an absolute path, place it in the CSV directory
    if not os.path.isabs(filename):
        return os.path.join(csv_dir, os.path.basename(filename))
    return filename

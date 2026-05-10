"""
Logging Configuration Module
----------------------------
Configures the application-wide logging strategy to meet Optasia's strict requirements.
Key features:
- Implements the mandatory log pattern for severity, timestamp, thread, and location.
- Dual-handler setup: Standard Output (stdout) for container logs and File system for persistence.
- Thread-safe logger initialization.
"""

import logging
import sys
import os
from typing import Optional


def setup_app_logger(name: str) -> logging.Logger:
    """
    Initializes and configures a logger instance with dual handlers.
    
    The log format strictly follows the Optasia pattern:
    %-5p,%d{yyyy-MM-dd HH:mm:ss,SSS} (%t) [%c] %m [%M: %L]%n
    
    Mapped to Python logging:
    - %-5p -> %(levelname)-5s (Severity)
    - %d -> %(asctime)s.%(msecs)03d (Timestamp with milliseconds)
    - (%t) -> (%(threadName)s) (Thread name)
    - [%c] -> [%(name)s] (Logger/Component name)
    - %m -> %(message)s (The actual log message)
    - [%M: %L] -> [%(funcName)s: %(lineno)d] (Function name and Line number)
    
    Args:
        name: The name of the module or component creating the logger.
        
    Returns:
        logging.Logger: A pre-configured logger instance.
    """
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers if the logger is already initialized
    if logger.handlers:
        return logger

    # Set base logging level
    logger.setLevel(logging.INFO)
    
    # Precise format string to match the technical assignment requirements
    log_format = (
        "%(levelname)-5s,%(asctime)s.%(msecs)03d (%(threadName)s) "
        "[%(name)s] %(message)s [%(funcName)s: %(lineno)d]"
    )
    date_format = "%Y-%m-%d %H:%M:%S"
    
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # 1. Console Handler (Standard Output)
    # Essential for Docker container monitoring and cloud-native logging (ELK/Splunk)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (Persistence)
    # Writes to the mapped volume for long-term storage and manual audits
    log_dir = "/app/logs"
    try:
        # Check if the log directory exists (mapped via Docker volume)
        if os.path.exists(log_dir):
            file_handler = logging.FileHandler(f"{log_dir}/optasia_api.log")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    except Exception as e:
        # Fallback to console only if file system is inaccessible
        print(f"Warning: Could not initialize file handler at {log_dir}: {e}", file=sys.stderr)

    return logger
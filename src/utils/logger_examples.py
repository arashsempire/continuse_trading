import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        logging.StreamHandler(),         # Log to console
    ],
)

logger = logging.getLogger(__name__)
logger.info("This is an info message.")
logger.error("This is an error message.")



#=========================================================================================



import json
import logging
from pythonjsonlogger import jsonlogger

# Configure JSON logging
logger = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# Log structured data
logger.info("User  logged in", extra={"user_id": 123, "action": "login", "status": "success"})

#=========================================================================================




logger.debug("Debugging information.")
logger.info("Application started.")
logger.warning("Low disk space.")
logger.error("Failed to connect to database.")
logger.critical("Server is down!")




#=========================================================================================

logger.info(
    "Request processed",
    extra={
        "timestamp": "2023-10-01T12:34:56Z",
        "level": "INFO",
        "service": "auth-service",
        "request_id": "abc123",
        "user_id": 123,
        "environment": "production",
    },
)


#=========================================================================================

def mask_sensitive_data(data):
    return "***" if data else None

logger.info(
    "User  data processed",
    extra={
        "user_id": 123,
        "email": mask_sensitive_data("user@example.com"),
    },
)


#=========================================================================================

import logging
from logging.handlers import RotatingFileHandler

# Configure log rotation
handler = RotatingFileHandler(
    "app.log", maxBytes=10 * 1024 * 1024, backupCount=5  # 10 MB per file, keep 5 backups
)
logger = logging.getLogger(__name__)
logger.addHandler(handler)

# logger.info("This log entry will be



#=========================================================================================



import logging

# Set log level
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
logger.debug("This will not be logged.")  # DEBUG < INFO
logger.info("This will be logged.")       # INFO >= INFO




#=========================================================================================




import logging

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# File handler (logs INFO and above)
file_handler = logging.FileHandler("app.log")
file_handler.setLevel(logging.INFO)

# Console handler (logs ERROR and above)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

# Add formatters
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Log messages
logger.debug("Debug message.")  # Only logged if level is DEBUG
logger.info("Info message.")    # Logged to file
logger.error("Error message.")  # Logged to file and console



#=========================================================================================


# View only ERROR logs in a file
grep "ERROR" app.log



#=========================================================================================


import logging
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

# Configure Sentry
sentry_logging = LoggingIntegration(
    level=logging.INFO,        # Capture INFO and above
    event_level=logging.ERROR  # Send ERROR and above to Sentry
)



#=========================================================================================


import logging

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# File handler (logs INFO and above)
file_handler = logging.FileHandler("app.log")
file_handler.setLevel(logging.INFO)

# Console handler (logs ERROR and above)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

# Add formatters
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Log messages
logger.debug("Debug message.")  # Only logged if level is DEBUG
logger.info("Info message.")    # Logged to file
logger.error("Error message.")  # Logged to file and console



#=========================================================================================



import logging
from logging.handlers import RotatingFileHandler

# Create a custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set the base log level

# Handler 1: General logs (INFO and above)
general_handler = RotatingFileHandler(
    "general.log", maxBytes=10 * 1024 * 1024, backupCount=5  # 10 MB per file, keep 5 backups
)
general_handler.setLevel(logging.INFO)  # Only log INFO and above
general_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
general_handler.setFormatter(general_formatter)

# Handler 2: Error logs (ERROR and above)
error_handler = RotatingFileHandler(
    "error.log", maxBytes=10 * 1024 * 1024, backupCount=5  # 10 MB per file, keep 5 backups
)
error_handler.setLevel(logging.ERROR)  # Only log ERROR and above
error_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
error_handler.setFormatter(error_formatter)

# Add handlers to the logger
logger.addHandler(general_handler)
logger.addHandler(error_handler)

# Example usage
logger.info("This is an info message.")  # Logged to general.log
logger.error("This is an error message.")  # Logged to both general.log and error.log


from utils.logger import logger

def main():
    logger.info("Starting the application...")
    try:
        # Simulate some work
        result = 10 / 2
        logger.info(f"Calculation result: {result}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Application finished.")

if __name__ == "__main__":
    main()




#=========================================================================================



from logging.handlers import TimedRotatingFileHandler

# Handler 3: Daily rotating logs
daily_handler = TimedRotatingFileHandler(
    "daily.log", when="midnight", interval=1, backupCount=7  # Rotate daily, keep 7 backups
)
daily_handler.setLevel(logging.INFO)
daily_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
daily_handler.setFormatter(daily_formatter)

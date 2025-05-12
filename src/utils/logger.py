import structlog
import logging
import sys


class BaseLogger:
    def __init__(self):
        # Get the class name and bind it to the logger
        self.log = structlog.get_logger().bind(class_name=self.__class__.__name__)


# def configure_logging(lvl: int =3):
def configure_logging(lvl=logging.WARNING):
    '''
    :lvl: 0 - DEBUG, 1 - INFO, 2 - WARNING, 3 - ERROR,
    '''
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),  # Add ISO timestamps
            structlog.processors.add_log_level,           # Add log level
            structlog.processors.StackInfoRenderer(),     # Add stack info for exceptions
            structlog.processors.format_exc_info,         # Format exceptions
            # structlog.stdlib.ProcessorFormatter.wrap_for_formatter,  # Wrap for logging module
            structlog.dev.ConsoleRenderer()
        ],
        # context_class=dict,                               # Use dict for context
        logger_factory=structlog.stdlib.LoggerFactory(),  # Use standard logging
        wrapper_class=structlog.stdlib.BoundLogger,       # Use BoundLogger for context
        cache_logger_on_first_use=True,                   # Cache loggers for performance
    )

    # Configure the standard logging module
    # formatter = structlog.stdlib.ProcessorFormatter(
    #     processor=structlog.processors.JSONRenderer(),  # Output as JSON
    # )

    handler = logging.StreamHandler(sys.stdout)  # Log to stdout
    # handler.setFormatter(formatter)

    file_handler = logging.FileHandler("app.log")  # Log to a file
    # file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(lvl)
    # structlog.configure(
    # wrapper_class=structlog.make_filtering_bound_logger(lvl*10)
    # )


# Define a custom processor to filter debug logs
def debug_log_filter(_, method_name, event_dict):
    if method_name == "debug":
        return event_dict  # Allow debug logs
    raise structlog.DropEvent  # Drop non-debug logs


# Define a custom processor to filter debug logs
def info_log_filter(_, method_name, event_dict):
    if method_name == "info":
        return event_dict  # Allow debug logs
    raise structlog.DropEvent  # Drop non-debug logs


# Define a custom processor to filter debug logs
def error_log_filter(_, method_name, event_dict):
    if method_name == "error":
        return event_dict  # Allow debug logs
    raise structlog.DropEvent  # Drop non-debug logs


# Define a custom processor to filter debug logs
def warning_log_filter(_, method_name, event_dict):
    if method_name == "warning":
        return event_dict  # Allow debug logs
    raise structlog.DropEvent  # Drop non-debug logs


# Define a custom processor to filter debug logs
def critical_log_filter(_, method_name, event_dict):
    if method_name == "critical":
        return event_dict  # Allow debug logs
    raise structlog.DropEvent  # Drop non-debug logs


# # Configure structlog
# structlog.configure(
#     processors=[
#         debug_log_filter,  # Filter out non-debug logs
#         structlog.processors.add_log_level,  # Add log level to the log
#         structlog.processors.JSONRenderer(),  # Render logs as JSON
#     ],
#     context_class=dict,
#     logger_factory=structlog.PrintLoggerFactory(),  # Print logs to stdout
# )

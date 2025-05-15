import structlog
import logging
import sys


# Define a base logger class that automatically binds the class name
class BaseLogger:
    def __init__(self):
        """Initializes the logger and binds the class name."""
        self.log = structlog.get_logger().bind(class_name=self.__class__.__name__)


# Function to configure logging settings for the application
def configure_logging(log_level=logging.INFO):
    """
    Configures structlog and standard logging.

    Args:
        log_level (int): The minimum logging level to output (e.g., logging.DEBUG,
        logging.INFO).
                         Defaults to logging.INFO.
    """
    # Basic validation for log level
    if not isinstance(log_level, int):
        print(f"Invalid log level type: {type(log_level)}. Defaulting to INFO.")
        log_level = logging.INFO

    # Configure structlog processors
    structlog.configure(
        processors=[
            # Merge context variables
            structlog.contextvars.merge_contextvars,
            # Add log level (e.g., 'info', 'warning')
            structlog.processors.add_log_level,
            # Render stack info for exceptions
            structlog.processors.StackInfoRenderer(),
            # Format exception info
            structlog.processors.format_exc_info,
            # Add ISO timestamp (local time)
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            # Pretty-print logs to console with colors
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the standard library logging (which structlog will use)
    # This handler outputs to stdout and uses the ConsoleRenderer for colorful output
    console_handler = logging.StreamHandler(sys.stdout)
    # The formatter is important here for structlog to correctly process and colorize
    # logs from the standard library logger.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        # Processors for the formatter, typically a subset of the global processors
        # that prepare the log record for rendering.
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
        ],
    )
    console_handler.setFormatter(formatter)

    # Optional: File handler if you want to also log to a file (uncomment to enable)
    # file_handler = logging.FileHandler("application.log")
    # file_formatter = structlog.stdlib.ProcessorFormatter(
    #     processor=structlog.processors.JSONRenderer(),
    # )
    # file_handler.setFormatter(file_formatter)

    # Get the root logger and configure it
    root_logger = logging.getLogger()
    # Clear existing handlers (optional, prevents duplicate logs if run multiple times)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    # root_logger.addHandler(file_handler) # Uncomment to add file handler
    root_logger.setLevel(log_level)  # Set the minimum level for the root logger

    # Initial log message to confirm configuration
    initial_log = structlog.get_logger("LoggerConfig")
    initial_log.info("Logging configured", level=logging.getLevelName(log_level))


if __name__ == "__main__":
    configure_logging(logging.DEBUG)  # Configure for DEBUG level

    log = structlog.get_logger("ExampleApp")
    log.debug("This is a debug message.", data={"key": "value"})
    log.info("This is an info message.")
    log.warning("This is a warning.")
    log.error("This is an error.")
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("Caught an exception.")

    class MyService(BaseLogger):
        def do_something(self):
            self.log.info("Doing something in MyService.")

    service = MyService()
    service.do_something()

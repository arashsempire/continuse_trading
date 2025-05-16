import structlog
import logging
import sys


class BaseLogger:
    """
    A base class that provides a structlog logger instance bound with the class name.
    Subclasses can inherit from this to get a pre-configured logger.
    """

    def __init__(self):
        """Initializes the logger and binds the class name."""
        self.log = structlog.get_logger().bind(class_name=self.__class__.__name__)


def configure_logging(log_level=logging.INFO):
    """
    Configures structlog and standard Python logging for the application.

    This function sets up processors for structlog to enable features like
    context variable merging, log level addition, stack info rendering,
    exception formatting, ISO timestamping, and colored console output.
    It also configures the root logger of Python's standard logging module.

    Args:
        log_level (int, optional): The minimum logging level to output
                                   (e.g., logging.DEBUG, logging.INFO).
                                   Defaults to logging.INFO.
    """
    # Basic validation for log level type
    if not isinstance(log_level, int):
        # Using print here as logger might not be configured yet or to avoid self-logging issues.
        print(
            f"Warning: Invalid log level type: {type(log_level)}. Defaulting to INFO."
        )
        log_level = logging.INFO

    # Configure structlog processors
    structlog.configure(
        processors=[
            # Add context variables from structlog.contextvars
            structlog.contextvars.merge_contextvars,
            # Add the log level to the event dict.
            structlog.processors.add_log_level,
            # If log_level is too low, abort processing.
            structlog.stdlib.filter_by_level,
            # Add a timestamp in ISO format.
            structlog.processors.TimeStamper(fmt="iso", utc=False),  # Local time
            # Render stack information for exceptions.
            structlog.processors.StackInfoRenderer(),
            # If the "exc_info" key in the event dict is true, replace it with a formatted exception.
            structlog.processors.format_exc_info,
            # # If the "stack_info" key is true, replace it with a formatted stack trace.
            # structlog.processors.format_stack_info,
            # Perform %-string formatting.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # `logger_factory` is used to create wrapped loggers that are compatible with
        # standard logging.
        logger_factory=structlog.stdlib.LoggerFactory(),
        # `wrapper_class` is the bound logger that wraps loggers returned from
        # `logger_factory`. This one formats the event dict into a string.
        wrapper_class=structlog.stdlib.BoundLogger,
        # Effectively cache logger instances for performance.
        cache_logger_on_first_use=True,
    )

    # Configure the standard logging module (root logger)
    # The formatter for the console handler will use structlog's dev renderer.
    formatter = structlog.stdlib.ProcessorFormatter(
        # These run on ALL entries entering standard logging.
        processor=structlog.dev.ConsoleRenderer(colors=True),
        # These are only processors for `structlog` records.
        foreign_pre_chain=[structlog.processors.EventRenamer("message", "event")],
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Get the root logger and configure it
    root_logger = logging.getLogger()

    # Clear existing handlers to prevent duplicate logs if this function is called multiple times
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.setLevel(log_level)  # Set the minimum level for the root logger

    # Initial log message to confirm configuration
    # Use a specific logger for this message to distinguish it
    initial_log = structlog.get_logger("LoggerConfiguration")
    initial_log.info(
        "Logging configured successfully",
        configured_level=logging.getLevelName(log_level),
    )


# Example usage (typically called once at application startup)
if __name__ == "__main__":
    # Configure logging to DEBUG level for demonstration
    configure_logging(logging.DEBUG)

    # Get a logger for the current module or a specific name
    log = structlog.get_logger("ExampleApp")

    # Demonstrate different log levels
    log.debug("This is a debug message.", data={"key": "debug_value"}, user_id=123)
    log.info("This is an info message.", operation="example_op")
    log.warning("This is a warning message.", issue="potential_problem")
    log.error("This is an error message.", error_code=500)

    # Demonstrate exception logging
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception(
            "A ZeroDivisionError occurred."
        )  # Automatically includes exc_info

    # Example of using BaseLogger in a class
    class MyService(BaseLogger):
        def __init__(self):
            super().__init__()  # Initializes self.log
            self.log.info("MyService instance created.")

        def do_something(self, item_id: int):
            self.log.info(
                "Doing something in MyService.", item_id=item_id, status="started"
            )
            # ... some logic ...
            self.log.debug("Intermediate step completed.", detail="some_detail")
            self.log.info(
                "Finished doing something in MyService.",
                item_id=item_id,
                status="completed",
            )

    service_instance = MyService()
    service_instance.do_something(item_id=42)

    # Example of logging with context
    with structlog.contextvars.bound_contextvars(request_id="req-789"):
        log.info("Message within a specific request context.")
        service_instance.do_something(item_id=99)

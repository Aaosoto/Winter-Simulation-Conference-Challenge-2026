"""
A unified logging system based on loguru with extensible formatters.

This module provides a flexible logging infrastructure with support for:
- Multiple output handlers (console, file)
- Customizable formatters (default, simple, detailed)
- Context binding and advanced options
- Simplified placeholder syntax transformation
"""

from __future__ import annotations

import enum
import os
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Self

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger, Record

__all__ = [
    'get_logger',
    'reset_logger',
    'LogLevel',
    'UnifiedLogger',
    'LogFormatter',
    'DefaultFormatter',
    'SimpleFormatter',
    'DetailedFormatter',
]

# =============================================================================
# Placeholder Transformation
# =============================================================================

def transform_log_message(msg: str) -> str:
    """
    Transform simplified placeholders to loguru record format.
    
    Converts three placeholder syntaxes to loguru's record format:
    - {[[key]]} → {record[extra][key]}
    - {[key]} → {record[key]}
    - {key} → {key} (unchanged)
    
    Transformation rules:
    - {[[key]]} or {[[key:format]]} → {record[extra][key]} or {record[extra][key]:format}
    - {[key]} or {[key:format]} → {record[key]} or {record[key]:format}
    - {key} or {key:format} → {key} or {key:format} (no transformation)
    
    Parameters
    ----------
    msg : str
        Message with simplified placeholders.
    
    Returns
    -------
    str
        Message with loguru record format.
    
    Examples
    --------
    Bound context variables (via bind()):
    
    >>> transform_log_message("{[[user]]} at {[[location]]}")
    "{record[extra][user]} at {record[extra][location]}"
    
    Built-in loguru fields:
    
    >>> transform_log_message("{[function]} at {[time]}")
    "{record[function]} at {record[time]}"
    
    Keyword argument variables:
    
    >>> transform_log_message("User {user} with status {status}")
    "User {user} with status {status}"
    
    Mixed usage:
    
    >>> transform_log_message("{[[owner]]} called {[function]} - {status}")
    "{record[extra][owner]} called {record[function]} - {status}"
    
    With format specifiers:
    
    >>> transform_log_message("{[time]:%H:%M:%S} - {[[value]]:.2f} - {count}")
    "{record[time]:%H:%M:%S} - {record[extra][value]:.2f} - {count}"
    """
    # Skip if already has record access patterns
    if 'record[' in msg:
        return msg

    # Pattern 1: Transform {[[key]]} or {[[key:format]]} → {record[extra][key]} or {record[extra][key]:format}
    # Process FIRST to handle double-bracket syntax for bind() context
    pattern_double_bracket = r'\{\[\[([a-zA-Z_]\w*)\]\](?::([^}]+))?\}'

    def replacer_double_bracket(match: re.Match[str]) -> str:
        key, fmt = match.group(1), match.group(2)
        if fmt:
            return f'{{record[extra][{key}]:{fmt}}}'
        return f'{{record[extra][{key}]}}'

    msg = re.sub(pattern_double_bracket, replacer_double_bracket, msg)

    # Pattern 2: Transform {[key]} or {[key:format]} → {record[key]} or {record[key]:format}
    # Process SECOND to handle single-bracket syntax for built-in fields
    pattern_single_bracket = r'\{\[([a-zA-Z_]\w*)\](?::([^}]+))?\}'

    def replacer_single_bracket(match: re.Match[str]) -> str:
        key, fmt = match.group(1), match.group(2)
        if fmt:
            return f'{{record[{key}]:{fmt}}}'
        return f'{{record[{key}]}}'

    msg = re.sub(pattern_single_bracket, replacer_single_bracket, msg)

    # Pattern 3: {key} remains unchanged for keyword arguments
    # No transformation needed

    return msg


# =============================================================================
# Log Formatter Base Class
# =============================================================================

class LogLevel(str, enum.Enum):
    """
    Enumeration of log levels for unified logging system.
    
    Inherits from str to enable direct string comparison and usage
    in loguru methods without explicit conversion.
    
    Attributes
    ----------
    TRACE : str
        Most detailed diagnostic information for tracing execution flow.
    DEBUG : str
        Detailed diagnostic information useful during development.
    INFO : str
        General informational messages about application progress.
    SUCCESS : str
        Successful completion of significant operations.
    WARNING : str
        Potentially problematic situations that don't prevent execution.
    ERROR : str
        Error events that might still allow continued execution.
    CRITICAL : str
        Very severe errors that may cause application termination.
    """
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __str__(self) -> str:
        """
        Return the string value for direct usage.
        """
        return self.value


# =============================================================================
# Log Formatter Base Class
# =============================================================================

class LogFormatter(ABC):
    """
    Abstract base class for log formatters.
    
    Defines the interface that all custom log formatters must implement.
    Subclasses should provide a format string compatible with loguru's
    formatting system.
    """

    @abstractmethod
    def get_format(self) -> str:
        """
        Return the format string for loguru.
        
        Returns
        -------
        str
            The format string with loguru placeholders (e.g., {time}, {level}, {message}).
        """
        ...


# =============================================================================
# Built-in Formatter Implementations
# =============================================================================

class DefaultFormatter(LogFormatter):
    """
    Default log formatter with timestamp, level, and message.
    
    Provides a balanced format suitable for most use cases, with optional
    inclusion of process/thread IDs and source location information.
    """

    def __init__(
        self,
        time_format: str = "YYYY-MM-DD HH:mm:ss",
        include_process: bool = False,
        include_thread: bool = False,
        include_location: bool = False,
        include_exception: bool = False,
    ) -> None:
        """
        Initialize the default formatter.
        
        Parameters
        ----------
        time_format : str, optional
            Time format string for loguru. Defaults to "YYYY-MM-DD HH:mm:ss".
            Common formats:
            - "YYYY-MM-DD HH:mm:ss.SSSSSSZ" (full with timezone, microseconds)
            - "YYYY-MM-DD HH:mm:ss.SSS" (milliseconds)
            - "YYYY-MM-DD HH:mm:ss" (seconds)
            - "HH:mm:ss.SSS" (time only with milliseconds)
            - "HH:mm:ss" (time only)
        include_process : bool, optional
            Whether to include process ID in the log. Defaults to False.
        include_thread : bool, optional
            Whether to include thread ID in the log. Defaults to False.
        include_location : bool, optional
            Whether to include source location (module, function, line) in the log.
            Defaults to False.
        include_exception : bool, optional
            Whether to include exception information in the log. Defaults to False.
        """
        self.time_format = time_format
        self.include_process = include_process
        self.include_thread = include_thread
        self.include_location = include_location
        self.include_exception = include_exception

    def get_format(self) -> str:
        """
        Build format string based on configuration.
        
        Returns
        -------
        str
            Pipe-separated format string with configured components.
        """
        parts = [f'<green>{{time:{self.time_format}}}</green>']

        if self.include_process:
            parts.append('{process:<5}')
        if self.include_thread:
            parts.append('{thread:<5}')

        parts.append('<level>{level:<8}</level>')

        if self.include_location:
            parts.append('<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>')

        parts.append('{message}')

        if self.include_exception:
            parts.append('{exception}')

        return ' | '.join(parts)


class SimpleFormatter(LogFormatter):
    """
    Simple log formatter with minimal information.
    
    Includes only time (HH:mm:ss), level, and message for concise output.
    Suitable for development environments or when detailed context is unnecessary.
    """

    def get_format(self) -> str:
        """
        Return minimal format string.
        
        Returns
        -------
        str
            Concise format with time, level, and message only.
        """
        return '<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}'


class DetailedFormatter(LogFormatter):
    """
    Detailed log formatter with full context.
    
    Includes all available information: timestamp, process/thread IDs,
    level, source location, and message. Suitable for production logging
    or debugging complex issues.
    """

    def get_format(self) -> str:
        """
        Return comprehensive format string.
        
        Returns
        -------
        str
            Format with all available context information.
        """
        parts = [
            '<green>{time:YYYY-MM-DD HH:mm:ss.SSSSSSZ}</green>',
            '{process:<5}',
            '{thread:<5}',
            '<level>{level:<8}</level>',
            '<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>',
            '{message}',
            '{exception}',
        ]
        return ' | '.join(parts)


# =============================================================================
# Unified Logger Implementation
# =============================================================================

class UnifiedLogger:
    """
    A unified logger based on loguru with extensible formatters.
    
    This class serves dual purposes:
    1. As a configurator: setup handlers and formatters via add_*_handler methods
    2. As a logger: call logging methods with automatic message transformation
    
    The bind() and opt() methods return new instances wrapping the underlying
    loguru logger, enabling method chaining while maintaining the same API.
    
    Message Placeholder Patterns
    ---------------------------
    - {[[key]]}: For context bound via bind(), transformed to {record[extra][key]} by transform_log_message.
    - {[key]}: For built-in loguru fields, transformed to {record[key]}.
    - {key}: For keyword arguments passed to log methods, remains unchanged.
    
    Usage Examples
    --------------
    Setup and basic usage:
    
    >>> unified_logger = UnifiedLogger()
    >>> unified_logger.add_console_handler()
    
    Pattern 1 - bind() + {[[key]]} + opt(record=True):
    
    >>> unified_logger.opt(record=True).bind(user="alice").info("{[[user]]} logged in")
    
    Pattern 2 - kwargs + {key} (simpler, recommended):
    
    >>> unified_logger.info("User {user} logged in", user="alice")
    
    Pattern 3 - Mixed usage:
    
    >>> unified_logger.opt(record=True).bind(session="xyz").info(
    ...     "{[[session]]}: {user} in {[function]}", user="bob"
    ... )
    
    See transform_log_message() for details on placeholder transformation.
    """

    # -------------------------------------------------------------------------
    # Initialization and Configuration
    # -------------------------------------------------------------------------

    def __init__(
        self,
        name: str = "app",
        _wrapped_logger: Logger | None = None,
        _opt_kwargs: dict | None = None,
    ) -> None:
        """
        Initialize the unified logger.
        
        Parameters
        ----------
        name : str, optional
            The application name for identification. Defaults to "app".
        _wrapped_logger : Logger | None, optional
            Internal: wrapped loguru logger instance. Users should not set this.
        _opt_kwargs : dict | None, optional
            Internal: options for the wrapped logger. Users should not set this.
        """
        self.name = name
        self._handler_ids: list[int] = []
        self._configured = False
        self._wrapped_logger = _wrapped_logger or logger
        self._opt_kwargs = _opt_kwargs or {}

    def reset(self) -> Self:
        """
        Reset the logger by removing all handlers.
        
        Clears all registered handlers and resets configuration state.
        Useful when reconfiguring the logger or in testing scenarios.
        
        Returns
        -------
        Self
            This instance for method chaining.
        """
        for handler_id in self._handler_ids:
            logger.remove(handler_id)
        logger.remove()
        self._handler_ids.clear()
        self._configured = False
        return self

    # -------------------------------------------------------------------------
    # Handler Registration
    # -------------------------------------------------------------------------

    def add_console_handler(
        self,
        level: str = LogLevel.INFO,
        formatter: LogFormatter | None = None,
        filter_func: Callable[[Record], bool] | None = None,
        colorize: bool = True,
    ) -> Self:
        """
        Add a console output handler.
        
        Registers a handler that outputs log messages to stdout (console).
        Supports colorized output via ANSI escape codes.
        
        Parameters
        ----------
        level : str, optional
            Minimum log level for this handler. Defaults to LogLevel.INFO.
        formatter : LogFormatter | None, optional
            Custom formatter instance. Defaults to DefaultFormatter if None.
        filter_func : Callable[[Record], bool] | None, optional
            Custom filter function for selective logging. Defaults to None.
        colorize : bool, optional
            Whether to colorize console output with ANSI codes. Defaults to True.
        
        Returns
        -------
        Self
            This instance for method chaining.
        """
        formatter = formatter or DefaultFormatter()

        handler_id = logger.add(
            sink=sys.stdout,
            level=level.upper(),
            format=formatter.get_format(),
            filter=filter_func,
            colorize=colorize,
            enqueue=True,
        )
        self._handler_ids.append(handler_id)
        self._configured = True
        return self

    def add_file_handler(
        self,
        log_dir: str,
        level: str = "DEBUG",
        formatter: LogFormatter | None = None,
        filter_func: Callable[[Record], bool] | None = None,
        serialize: bool = False,
        rotation: str | None = None,
        retention: str | None = None,
        compression: str | None = None,
    ) -> Self:
        """
        Add a file output handler with optional rotation.
        
        Registers a handler that outputs log messages to files in the specified
        directory. Supports log rotation, retention policies, and compression.
        
        Parameters
        ----------
        log_dir : str
            The directory for log files. Created if it doesn't exist.
        level : str, optional
            Minimum log level for this handler. Defaults to "DEBUG".
        formatter : LogFormatter | None, optional
            Custom formatter. Defaults to DefaultFormatter with location info if None.
        filter_func : Callable[[Record], bool] | None, optional
            Custom filter function for selective logging. Defaults to None.
        serialize : bool, optional
            Whether to serialize logs to JSON format. Defaults to False.
        rotation : str | None, optional
            When to rotate log files (e.g., "500 MB", "1 week"). Defaults to None.
        retention : str | None, optional
            How long to keep old log files (e.g., "10 days"). Defaults to None.
        compression : str | None, optional
            Compression method for rotated files (e.g., "zip", "gz"). Defaults to None.
        
        Returns
        -------
        Self
            This instance for method chaining.
        """
        formatter = formatter or DefaultFormatter(include_location=True)

        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "{time:YYYY-MM-DD-HH-mm-ss}.log")

        handler_id = logger.add(
            sink=log_file,
            level=level.upper(),
            format=formatter.get_format(),
            filter=filter_func,
            colorize=False,
            serialize=serialize,
            enqueue=True,
            rotation=rotation,
            retention=retention,
            compression=compression,
        )
        self._handler_ids.append(handler_id)
        self._configured = True
        return self

    # -------------------------------------------------------------------------
    # Context Binding and Options
    # -------------------------------------------------------------------------

    def bind(self, **kwargs) -> UnifiedLogger:
        """
        Bind extra context to the logger.
        
        Returns a new UnifiedLogger instance wrapping a bound loguru logger.
        Bound values are accessible via {[key]} syntax with opt(record=True).
        Context is preserved across subsequent log calls from the returned instance.
        
        Parameters
        ----------
        **kwargs
            Key-value pairs to bind as contextual information.
        
        Returns
        -------
        UnifiedLogger
            New instance with bound context, enabling method chaining.
        
        Examples
        --------
        >>> logger_with_user = unified_logger.bind(user="alice", session="xyz")
        >>> logger_with_user.opt(record=True).info("{[user]} started {[session]}")
        """
        bound_logger = self._wrapped_logger.bind(**kwargs)
        return UnifiedLogger(
            name=self.name,
            _wrapped_logger=bound_logger,
            _opt_kwargs=dict(self._opt_kwargs),
        )

    def opt(
        self,
        record: bool = False,
        depth: int = 0,
        exception: Exception | None = None,
        lazy: bool = False,
        colors: bool = False,
        raw: bool = False,
        capture: bool = True,
        ansi: bool = False,
        **extra,
    ) -> UnifiedLogger:
        """
        Configure logger options for advanced usage.
        
        Returns a new UnifiedLogger instance with specified options applied.
        Enables method chaining while maintaining automatic message transformation.
        Options affect how the next log call is processed.
        
        Parameters
        ----------
        record : bool, optional
            Whether to enable record formatting in messages. Defaults to False.
        depth : int, optional
            Stack depth adjustment for correct caller information. Defaults to 0.
        exception : Exception | None, optional
            Exception to log with full traceback. Defaults to None.
        lazy : bool, optional
            Whether to defer string formatting until log level check passes.
            Defaults to False.
        colors : bool, optional
            Whether to enable color tags in message (e.g., <red>text</red>).
            Defaults to False.
        raw : bool, optional
            Whether to log the raw message without formatting. Defaults to False.
        capture : bool, optional
            Whether to capture the logged message for testing/inspection. Defaults to True.
        ansi : bool, optional
            Whether to strip ANSI escape codes from message. Defaults to False.
        
        Returns
        -------
        UnifiedLogger
            New instance with options applied.
        
        Examples
        --------
        Enable record access and colors:
        
        >>> unified_logger.opt(record=True, colors=True).bind(
        ...     owner="sandbox"
        ... ).info("<red>{[owner]}</red> encountered error")
        
        Log with exception traceback:
        
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     unified_logger.opt(exception=e).error("Operation failed")
        """
        new_kwargs = dict(self._opt_kwargs)
        new_depth = new_kwargs.get("depth", 0) + depth
        new_kwargs["depth"] = new_depth
        for k, v in dict(
            record=record,
            exception=exception,
            lazy=lazy,
            colors=colors,
            raw=raw,
            capture=capture,
            ansi=ansi,
            **extra
        ).items():
            if v is not None:
                new_kwargs[k] = v
        opted_logger = self._wrapped_logger.opt(**new_kwargs)
        return UnifiedLogger(
            name=self.name,
            _wrapped_logger=opted_logger,
            _opt_kwargs=new_kwargs,
        )

    # -------------------------------------------------------------------------
    # Logging Methods
    # -------------------------------------------------------------------------

    def log(self, level: str | LogLevel, msg: str, *args, **kwargs) -> None:
        """
        Log a message at specified level with automatic transformation.
        
        Automatically transforms {[key]} placeholders when record mode is enabled.
        Supports standard {key} placeholders for kwargs and built-in fields.
        
        Parameters
        ----------
        level : str or LogLevel
            Log level as string (e.g., (e.g., "TRACE", "DEBUG", "INFO", "WARNING", "ERROR")
            or LogLevel enum.
        msg : str
            Message template with placeholders:
            - {[key]}: for bind() context (requires opt(record=True))
            - {key}: for kwargs or built-in loguru fields
        *args
            Positional arguments for message formatting.
        **kwargs
            Keyword arguments for message formatting.
        
        Examples
        --------
        Using kwargs (recommended):
        
        >>> unified_logger.log("info", "User {user} at {time}", user="alice")
        
        Using bind() with record mode:
        
        >>> unified_logger.opt(record=True).bind(user="alice").log(
        ...     "info", "{[user]} logged in"
        ... )
        
        Mixed usage:
        
        >>> unified_logger.opt(record=True).bind(session="xyz").log(
        ...     "info", "{[session]}: {user} active", user="alice"
        ... )
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.log(level.upper(), msg, *args, **kwargs)

    def trace(self, msg: str, *args, **kwargs) -> None:
        """
        Log a trace-level message with automatic transformation.
        
        Use for very detailed diagnostic information during development.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.trace(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        """
        Log a debug-level message with automatic transformation.
        
        Use for detailed diagnostic information useful during development.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        """
        Log an info-level message with automatic transformation.
        
        Use for general informational messages about application progress.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.info(msg, *args, **kwargs)

    def success(self, msg: str, *args, **kwargs) -> None:
        """
        Log a success-level message with automatic transformation.
        
        Use to highlight successful completion of significant operations.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.success(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        """
        Log a warning-level message with automatic transformation.
        
        Use for potentially problematic situations that don't prevent execution.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """
        Log an error-level message with automatic transformation.
        
        Use for error events that might still allow continued execution.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        """
        Log a critical-level message with automatic transformation.
        
        Use for very severe error events that may cause application termination.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        """
        Log an exception with full traceback and automatic transformation.
        
        Should be called from an exception handler. Logs at ERROR level
        with complete stack trace information for debugging.
        """
        if self._opt_kwargs.get("record", False):
            msg = transform_log_message(msg)
        opt_kwargs = dict(self._opt_kwargs)
        opt_kwargs["depth"] = opt_kwargs.get("depth", 0) + 1
        local_logger = self._wrapped_logger.opt(**opt_kwargs)
        local_logger.exception(msg, *args, **kwargs)


# =============================================================================
# Global Singleton Instance and Accessor Functions
# =============================================================================

_unified_logger_instance: UnifiedLogger | None = None
"""Global singleton instance."""


def get_logger(name: str = "app") -> UnifiedLogger:
    """
    Get or create the global UnifiedLogger singleton instance.
    
    This function ensures only one UnifiedLogger instance exists throughout
    the application lifecycle. The underlying loguru logger is thread-safe.
    
    Parameters
    ----------
    name : str, optional
        Application name (only used on first call). Defaults to "app".
        Subsequent calls ignore this parameter and return the existing instance.
    
    Returns
    -------
    UnifiedLogger
        The global singleton instance.
    
    Examples
    --------
    Get the logger and configure it:
    
    >>> logger = get_logger("my_app")
    >>> logger.add_console_handler()
    >>> logger.info("Application started")
    
    Subsequent calls return the same instance:
    
    >>> logger2 = get_logger("different_name")  # name ignored
    >>> assert logger is logger2  # True
    
    Notes
    -----
    The logger name can only be set on first initialization. Use `reset_logger()`
    if you need to create a new instance with a different name.
    """
    global _unified_logger_instance
    if _unified_logger_instance is None:
        _unified_logger_instance = UnifiedLogger(name=name)
    return _unified_logger_instance


def reset_logger() -> None:
    """
    Reset the global UnifiedLogger singleton instance.
    
    Removes all handlers from global singleton instance and destroys it.
    The next call to `get_logger()` will create a fresh instance.
    
    This is primarily useful for:
    - Testing scenarios where you need clean state between tests
    - Reconfiguring the logger with different settings
    - Changing the application name after initialization
    
    Examples
    --------
    Reset between test cases:
    
    >>> def test_logging():
    ...     reset_logger()  # Clean slate
    ...     logger = get_logger("test_app")
    ...     logger.add_console_handler()
    ...     # Run test...
    
    Reconfigure with new name:
    
    >>> reset_logger()
    >>> new_logger = get_logger("production_app")
    
    Warnings
    --------
    This will affect all code that uses `get_logger()`. Any existing
    references to the old logger instance will still work but may behave
    unexpectedly after reset.
    """
    global _unified_logger_instance
    if _unified_logger_instance is not None:
        _unified_logger_instance.reset()
        _unified_logger_instance = None

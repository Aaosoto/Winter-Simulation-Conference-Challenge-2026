"""
A flexible output recording system based on the third-party library `loguru` with extensible formats.

This module provides a framework for recording structured data to files in various formats
(CSV, JSON, TSV) with support for rotation, retention, and compression.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Self

from loguru import logger

__all__ = [
    'OutputRecorder',
    'OutputFormatter',
    'CsvFormatter',
    'JsonFormatter',
    'TsvFormatter',
]

# =============================================================================
# Output Formatter Base Class
# =============================================================================

class OutputFormatter(ABC):
    """
    Abstract base class for output formatters.
    
    This class defines the interface that all output formatters must implement
    to support different output formats (CSV, JSON, TSV, etc.).
    """

    @abstractmethod
    def format_header(self, columns: Sequence[str]) -> str | None:
        """
        Format the header line for the output file.
        
        Parameters
        ----------
        columns : Sequence[str]
            The column names to include in the header.
        
        Returns
        -------
        str | None
            The formatted header string, or None if the format doesn't require headers.
        """
        ...

    @abstractmethod
    def format_record(self, record: dict[str, Any], columns: Sequence[str]) -> str:
        """
        Format a single data record for output.
        
        Parameters
        ----------
        record : dict[str, Any]
            The data record to format, containing column-value pairs.
        columns : Sequence[str]
            The ordered list of column names to include in the output.
        
        Returns
        -------
        str
            The formatted record as a single line string.
        """
        ...

    @abstractmethod
    def get_extension(self) -> str:
        """
        Get the file extension for this format.
        
        Returns
        -------
        str
            The file extension without the leading dot (e.g., 'csv', 'json').
        """
        ...


# =============================================================================
# Built-in Formatter Implementations
# =============================================================================

# -----------------------------------------------------------------------------
# CSV Formatter
# -----------------------------------------------------------------------------

class CsvFormatter(OutputFormatter):
    """
    CSV (Comma-Separated Values) output formatter.
    
    Supports customizable delimiters and optional field quoting.
    
    Examples
    --------
    >>> formatter = CsvFormatter(delimiter=",", quote=True)
    >>> formatter.format_header(["name", "age"])
    '"name","age"'
    >>> formatter.format_record({"name": "John", "age": 30}, ["name", "age"])
    '"John","30"'
    """

    def __init__(
        self,
        delimiter: str = ",",
        quote: bool = False,
        escape_char: str = "\\"
    ) -> None:
        """
        Initialize CSV formatter with custom options.

        Parameters
        ----------
        delimiter : str, optional
            The delimiter character for separating fields. Defaults to ",".
        quote : bool, optional
            Whether to wrap fields in double quotes. Defaults to False.
        escape_char : str, optional
            Character to use for escaping special characters. Defaults to "\\".
        """
        self.delimiter: str = delimiter
        self.quote: bool = quote
        self.escape_char: str = escape_char

    def _escape_value(self, value: str) -> str:
        """
        Escape special characters in a value.
        
        Parameters
        ----------
        value : str
            The value to escape.
            
        Returns
        -------
        str
            The escaped value.
        """
        # If quoting is disabled, check if quoting is necessary
        needs_quoting = self.delimiter in value or '\n' in value or '\r' in value or '"' in value

        if needs_quoting or self.quote:
            # Escape quotes by doubling them (standard CSV escaping)
            value = value.replace('"', '""')
            return f'"{value}"'

        return value

    def format_header(self, columns: Sequence[str]) -> str:
        """
        Format the CSV header line.
        
        Parameters
        ----------
        columns : Sequence[str]
            The column names.
        
        Returns
        -------
        str
            The formatted header line.
        """
        if self.quote:
            return self.delimiter.join(f'"{col}"' for col in columns)
        return self.delimiter.join(columns)

    def format_record(self, record: dict[str, Any], columns: Sequence[str]) -> str:
        """
        Format a single record as a CSV line.
        
        Parameters
        ----------
        record : dict[str, Any]
            The data record to format.
        columns : Sequence[str]
            The ordered column names.
        
        Returns
        -------
        str
            The formatted CSV line.
        """
        values = []
        for col in columns:
            value = record.get(col, "")
            # Convert to string and handle None
            value_str = "" if value is None else str(value)
            values.append(self._escape_value(value_str))

        return self.delimiter.join(values)

    def get_extension(self) -> str:
        """
        Get the CSV file extension.
        
        Returns
        -------
        str
            Returns 'csv'.
        """
        return "csv"


# -----------------------------------------------------------------------------
# JSON Formatter
# -----------------------------------------------------------------------------

class JsonFormatter(OutputFormatter):
    """
    JSON Lines (JSONL) output formatter.
    
    Outputs one JSON object per line, suitable for streaming and large datasets.
    
    Examples
    --------
    >>> formatter = JsonFormatter(indent=None)
    >>> formatter.format_record({"x": 1, "y": 2}, ["x", "y"])
    '{"x": 1, "y": 2}'
    """

    def __init__(
        self,
        ensure_ascii: bool = False,
        indent: int | None = None,
        sort_keys: bool = False
    ) -> None:
        """
        Initialize JSON formatter with serialization options.

        Parameters
        ----------
        ensure_ascii : bool, optional
            If True, escape non-ASCII characters. Defaults to False.
        indent : int | None, optional
            Number of spaces for indentation (None for compact output). Defaults to None.
        sort_keys : bool, optional
            Whether to sort dictionary keys. Defaults to False.
        """
        self.ensure_ascii: bool = ensure_ascii
        self.indent: int | None = indent
        self.sort_keys: bool = sort_keys

    def format_header(self, columns: Sequence[str]) -> str | None:
        """
        JSON Lines format doesn't use headers.
        
        Parameters
        ----------
        columns : Sequence[str]
            Unused for JSON format.
        
        Returns
        -------
        None
            JSON Lines doesn't require headers.
        """
        return None

    def format_record(self, record: dict[str, Any], columns: Sequence[str]) -> str:
        """
        Format a single record as a JSON object line.
        
        Parameters
        ----------
        record : dict[str, Any]
            The data record to format.
        columns : Sequence[str]
            The column names to include in the JSON object.
        
        Returns
        -------
        str
            The formatted JSON object as a single line.
        """
        # Only include specified columns and preserve order
        filtered_record = {col: record.get(col) for col in columns}
        return json.dumps(
            filtered_record,
            ensure_ascii=self.ensure_ascii,
            indent=self.indent,
            sort_keys=self.sort_keys,
            default=str  # Handle non-serializable objects
        )

    def get_extension(self) -> str:
        """
        Get the JSON Lines file extension.
        
        Returns
        -------
        str
            Returns 'jsonl'.
        """
        return "jsonl"


# -----------------------------------------------------------------------------
# TSV Formatter
# -----------------------------------------------------------------------------

class TsvFormatter(OutputFormatter):
    """
    TSV (Tab-Separated Values) output formatter.
    
    Uses tabs as delimiters instead of commas, suitable for data containing commas.
    
    Examples
    --------
    >>> formatter = TsvFormatter()
    >>> formatter.format_header(["col1", "col2"])
    'col1\\tcol2'
    >>> formatter.format_record({"col1": "a\\tb", "col2": "c"}, ["col1", "col2"])
    'a\\\\tb\\tc'
    """

    def __init__(self, escape_char: str = "\\") -> None:
        """
        Initialize TSV formatter.
        
        Parameters
        ----------
        escape_char : str, optional
            Character to use for escaping special characters. Defaults to "\\".
        """
        self.escape_char: str = escape_char

    def _escape_value(self, value: str) -> str:
        """
        Escape tabs and newlines in a value.
        
        Parameters
        ----------
        value : str
            The value to escape.
            
        Returns
        -------
        str
            The escaped value.
        """
        return (value
                .replace(self.escape_char, self.escape_char + self.escape_char)
                .replace("\t", self.escape_char + "t")
                .replace("\n", self.escape_char + "n")
                .replace("\r", self.escape_char + "r"))

    def format_header(self, columns: Sequence[str]) -> str:
        """
        Format the TSV header line.
        
        Parameters
        ----------
        columns : Sequence[str]
            The column names.
        
        Returns
        -------
        str
            The formatted header line with tab separators.
        """
        return "\t".join(columns)

    def format_record(self, record: dict[str, Any], columns: Sequence[str]) -> str:
        """
        Format a single record as a TSV line.
        
        Parameters
        ----------
        record : dict[str, Any]
            The data record to format.
        columns : Sequence[str]
            The ordered column names.
        
        Returns
        -------
        str
            The formatted TSV line.
        """
        values = []
        for col in columns:
            value = record.get(col, "")
            value_str = "" if value is None else str(value)
            values.append(self._escape_value(value_str))

        return "\t".join(values)

    def get_extension(self) -> str:
        """
        Get the TSV file extension.
        
        Returns
        -------
        str
            Returns 'tsv'.
        """
        return "tsv"


# =============================================================================
# Output Recorder Implementation
# =============================================================================

class OutputRecorder:
    """
    A flexible output recorder based on `loguru` with extensible formats.

    This class provides a high-level interface for recording structured data
    to files with support for multiple formats, file rotation, and automatic
    header management.

    Examples
    --------
    Basic usage with default values:

    >>> recorder = OutputRecorder("experiment_results")
    >>> recorder.initialize(
    ...     output_dir="./output",
    ...     columns={"time": 0.0, "value": 0, "status": ""}
    ... )
    >>> recorder.record(time=1.5, value=42)  # status will be ""
    >>> recorder.close()

    Using columns with different default values:
    
    >>> recorder = OutputRecorder("results")
    >>> recorder.initialize(
    ...     output_dir="./output",
    ...     columns={"time": 0.0, "value": None, "status": "pending"}
    ... )
    >>> recorder.record(time=1.5, value=100)  # status will be "pending"
    >>> recorder.close()

    Using context manager:

    >>> with OutputRecorder("results") as recorder:
    ...     recorder.initialize("./output", {"x": 0, "y": 0})
    ...     recorder.record(x=1, y=2)

    Batch recording for better performance:

    >>> recorder = OutputRecorder("data")
    >>> recorder.initialize("./output", {"id": 0, "value": 0})
    >>> records = [{"id": i, "value": i*2} for i in range(1000)]
    >>> recorder.record_batch(records)
    >>> recorder.close()

    Using custom formatter:

    >>> json_formatter = JsonFormatter(indent=2)
    >>> recorder = OutputRecorder("results", formatter=json_formatter)
    >>> recorder.initialize("./output", {"name": "", "score": 0})
    >>> recorder.record(name="Alice", score=95)
    >>> recorder.close()
    """

    # -------------------------------------------------------------------------
    # Initialization and Properties
    # -------------------------------------------------------------------------

    def __init__(
        self,
        tag: str,
        formatter: OutputFormatter | None = None
    ) -> None:
        """
        Initialize the output recorder with a unique tag.
        
        Parameters
        ----------
        tag : str
            A unique identifier for this recorder, used for filtering log records.
        formatter : OutputFormatter | None, optional
            The formatter to use for output. Defaults to CsvFormatter() if None.
            
        Raises
        ------
        ValueError
            If tag is empty or contains only whitespace.
        """
        if not tag or not tag.strip():
            raise ValueError("Tag cannot be empty or whitespace")

        self._tag: str = tag.strip()
        self._formatter: OutputFormatter = formatter or CsvFormatter()
        self._handler_id: int | None = None
        self._output_file: str | None = None
        self._column_specs: dict[str, Any] | None = None  # Map of column names to default values
        self._is_initialized: bool = False

        # Store initialization parameters for reset
        self._init_params: dict[str, Any] = {}

    @property
    def tag(self) -> str:
        """
        Get the unique identifier for this recorder.
        """
        return self._tag

    @property
    def formatter(self) -> OutputFormatter:
        """
        Get the current output formatter.
        """
        return self._formatter

    @property
    def output_file(self) -> str | None:
        """
        Get the current output file path, or None if not initialized.
        """
        return self._output_file

    @property
    def columns(self) -> tuple[str, ...] | None:
        """
        Get the column names, or None if not initialized.
        """
        if self._column_specs is None:
            return None
        return tuple(self._column_specs.keys())

    @property
    def defaults(self) -> dict[str, Any]:
        """
        Get the default values for columns.
        """
        if self._column_specs is None:
            return {}
        return self._column_specs.copy()

    @property
    def is_initialized(self) -> bool:
        """
        Check whether the recorder has been initialized.
        """
        return self._is_initialized

    # -------------------------------------------------------------------------
    # Configuration Methods
    # -------------------------------------------------------------------------

    def set_formatter(self, formatter: OutputFormatter) -> Self:
        """
        Set or change the output formatter.
        
        Parameters
        ----------
        formatter : OutputFormatter
            The new formatter to use for output.
            
        Returns
        -------
        Self
            Returns self for method chaining.
            
        Raises
        ------
        RuntimeError
            If trying to change formatter after initialization.
        """
        if self._is_initialized:
            raise RuntimeError("Cannot change formatter after initialization. Call close() or reset() first.")
        self._formatter = formatter
        return self

    def initialize(
        self,
        output_dir: str,
        columns: dict[str, Any],
        filename: str | None = None,
        level: str = "INFO",
        rotation: str | int | dt.timedelta | None = None,
        retention: str | int | dt.timedelta | None = None,
        compression: str | None = None,
        append: bool = False,
    ) -> str:
        """
        Initialize the output file and configure logging.

        This method sets up the output file, creates the directory if needed,
        and configures file rotation and retention policies.

        Parameters
        ----------
        output_dir : str
            The directory where output files will be created.
        columns : dict[str, Any]
            Dictionary mapping column names to their default values.
            The order of keys determines the column order in the output file.
            Requires Python 3.7+ for guaranteed dict ordering.
        filename : str | None, optional
            Custom filename for the output file (without extension).
            The appropriate extension will be added automatically.
            Defaults to {tag} if None.
        level : str, optional
            The minimum log level for output. Defaults to "INFO".
        rotation : str | int | dt.timedelta | None, optional
            When to rotate log files (e.g., "500 MB", "1 week"). Defaults to None.
        retention : str | int | dt.timedelta | None, optional
            How long to keep old log files (e.g., "10 days", 3). Defaults to None.
        compression : str | None, optional
            Compression method for rotated files (e.g., "zip", "gz"). Defaults to None.
        append : bool, optional
            Whether to append to existing file or overwrite. Defaults to False.

        Returns
        -------
        str
            The full path to the output file.
            
        Raises
        ------
        ValueError
            If columns is empty, contains duplicates, or contains invalid column names.
        RuntimeError
            If recorder is already initialized.
        TypeError
            If columns is not a dictionary.

        Examples
        --------
        >>> recorder.initialize("./output", {"id": 0, "name": "", "active": True})

        Notes
        -----
        This method requires Python 3.7+ to guarantee that the column order
        in the output file matches the order of keys in the columns dictionary.
        """
        if self._is_initialized:
            raise RuntimeError("OutputRecorder already initialized. Call close() or reset() first.")

        # Type check
        if not isinstance(columns, dict):
            raise TypeError(f"columns must be a dict, got {type(columns).__name__}")

        # Validate columns dictionary
        if not columns:
            raise ValueError("Columns dictionary cannot be empty")

        # Validate column names
        column_set = set()
        for col in columns.keys():
            if not isinstance(col, str) or not col:
                raise ValueError(f"Invalid column name: {col!r}")
            if col in column_set:
                raise ValueError(f"Duplicate column name: {col!r}")
            column_set.add(col)

        # Store column specifications
        self._column_specs = columns.copy()

        # Store initialization parameters for potential reset
        self._init_params = {
            'output_dir': output_dir,
            'columns': columns,
            'filename': filename,
            'level': level,
            'rotation': rotation,
            'retention': retention,
            'compression': compression,
            'append': append,
        }

        # Remove previous handler if exists
        if self._handler_id is not None:
            logger.remove(self._handler_id)

        # Determine output file path
        if filename is not None:
            filename = filename.strip()
        filename = filename or self._tag

        # Sanitize filename and add extension
        filename = filename.replace(" ", "_").replace("\t", "_")
        filename = f"{filename}.{self._formatter.get_extension()}"

        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        self._output_file = os.path.join(output_dir, filename)

        # Check if file exists to determine if header is needed
        file_exists = os.path.exists(self._output_file) and append

        # Add loguru handler with custom filter
        self._handler_id = logger.add(
            sink=self._output_file,
            level=level.upper(),
            format="{message}",
            filter=self._filter_record,
            colorize=False,
            enqueue=True,
            rotation=rotation,
            retention=retention,
            compression=compression,
            mode='a' if append else 'w',
        )

        # Write header if needed and file is new or not appending
        if not file_exists:
            cols = tuple(self._column_specs.keys())
            header = self._formatter.format_header(cols)
            if header is not None:
                self._write_raw(header)

        self._is_initialized = True

        return self._output_file

    def reset(self) -> None:
        """
        Reset the recorder by closing and re-initializing with the same parameters.
        
        This method closes the current output file and re-initializes it using
        the same parameters that were passed to the last `initialize()` call,
        effectively starting a new recording session.
        
        Raises
        ------
        RuntimeError
            If the recorder hasn't been initialized with `initialize()` yet.
        """
        if not self._init_params:
            raise RuntimeError("OutputRecorder not initialized. Call initialize() first.")

        # Close existing handler
        self.close()

        # Re-initialize with stored parameters
        self.initialize(**self._init_params)

    def close(self) -> None:
        """
        Close the output recorder and release file handles.
        
        This method should be called when you're done recording to ensure
        all data is flushed to disk and resources are released.
        """
        if self._handler_id is not None:
            logger.remove(self._handler_id)
            self._handler_id = None
        self._is_initialized = False

    # -------------------------------------------------------------------------
    # Internal Helper Methods
    # -------------------------------------------------------------------------

    def _filter_record(self, record: dict[str, Any]) -> bool:
        """
        Filter log records to only handle those with matching output tag.
        
        This is used internally by loguru to route records to the correct handler.
        
        Parameters
        ----------
        record : dict[str, Any]
            The log record from loguru.
            
        Returns
        -------
        bool
            True if this record should be handled by this recorder.
        """
        return record["extra"].get("output_tag") == self._tag

    def _write_raw(self, message: str) -> None:
        """
        Write a raw message to the output file.
        
        This is used internally to bypass record formatting.
        
        Parameters
        ----------
        message : str
            The pre-formatted message to write.
        """
        logger.opt(depth=2).bind(output_tag=self._tag).info(message)

    def _ensure_initialized(self) -> None:
        """
        Ensure the recorder is initialized before operations.
        
        Raises
        ------
        RuntimeError
            If the recorder hasn't been initialized.
        """
        if not self._is_initialized or self._column_specs is None:
            raise RuntimeError("OutputRecorder not initialized. Call initialize() first.")

    def _format_record(self, record: dict[str, Any]) -> str:
        """
        Format a record for output, applying default values.
        
        Parameters
        ----------
        record : dict[str, Any]
            The record to format.
            
        Returns
        -------
        str
            The formatted record string.
        """
        # Build full record with defaults, then override with provided values
        full_record = {}
        for col, default in self._column_specs.items():
            # Priority: provided value > default value
            full_record[col] = record.get(col, default)
        cols = tuple(self._column_specs.keys())
        return self._formatter.format_record(full_record, cols)

    # -------------------------------------------------------------------------
    # Recording Methods
    # -------------------------------------------------------------------------

    def record(self, **kwargs) -> None:
        """
        Record a single data point using keyword arguments.
        
        Parameters
        ----------
        **kwargs :
            Column-value pairs to record. Missing columns will be filled with default values.
        
        Raises
        ------
        RuntimeError
            If the recorder hasn't been initialized with `initialize()`.

        Examples
        --------
        >>> recorder.record(time=1.5, value=100, status="complete")
        """
        self._ensure_initialized()
        line = self._format_record(kwargs)
        self._write_raw(line)

    def record_dict(self, record: dict[str, Any]) -> None:
        """
        Record a single dictionary as a data point.
        
        Parameters
        ----------
        record : dict[str, Any]
            The record to write, containing column-value pairs.
            
        Raises
        ------
        RuntimeError
            If the recorder hasn't been initialized.
        
        Examples
        --------
        >>> recorder.record_dict({"time": 1.5, "value": 100})
        """
        self._ensure_initialized()
        line = self._format_record(record)
        self._write_raw(line)

    def record_batch(self, records: Sequence[dict[str, Any]]) -> None:
        """
        Record multiple data points in a single call.
        
        This is more efficient than calling `record()` multiple times
        for large batches of data, as it formats all records first
        then writes them in one operation.
        
        Parameters
        ----------
        records : Sequence[dict[str, Any]]
            A sequence of records to write.
            
        Raises
        ------
        RuntimeError
            If the recorder hasn't been initialized.
        
        Examples
        --------
        >>> records = [{"id": 1, "value": 10}, {"id": 2, "value": 20}]
        >>> recorder.record_batch(records)
        """
        self._ensure_initialized()

        if not records:
            return

        for record in records:
            line = self._format_record(record)
            self._write_raw(line)

    # -------------------------------------------------------------------------
    # Context Manager Support
    # -------------------------------------------------------------------------

    def __enter__(self) -> Self:
        """
        Enter context manager.
        
        Returns
        -------
        Self
            Returns self for use in with statements.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any
    ) -> None:
        """
        Exit context manager and close the recorder.
        
        Parameters
        ----------
        exc_type : type[BaseException] | None
            The exception type if an exception occurred.
        exc_val : BaseException | None
            The exception value if an exception occurred.
        exc_tb : Any
            The exception traceback if an exception occurred.
        """
        self.close()

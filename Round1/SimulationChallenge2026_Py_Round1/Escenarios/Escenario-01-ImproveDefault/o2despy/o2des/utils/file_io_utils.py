"""
File I/O utilities for O2DES framework.

This module provides convenient functions for file operations, including:
- Basic file opening with consistent encoding and permissions
- JSON file reading and writing with JSON5 support

Key Features:
    - Unified file handling with automatic encoding fallback (FileIoConfig.TEXT_ENCODING)
    - Secure file permissions via FileIoConfig.PERMISSION_MODE (owner read/write by default)
    - JSON5 parsing support (comments, trailing commas, etc.)
    - Cross-platform compatibility with pathlib support
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, TextIO

import pyjson5

from o2des.config import FileIoConfig

__all__ = [
    'fopen',
    'read_json',
    'write_json',
]

# =============================================================================
# Basic File Operations
# =============================================================================

def fopen(
    filename: str | Path,
    mode: Literal['r', 'w', 'w+', 'x', 'a', 'r+'],
    encoding: str | None = None,
) -> TextIO:
    """
    Open a file with consistent encoding and secure permissions.

    This function provides a unified interface for file operations with:
    - Automatic encoding fallback to FileIoConfig.TEXT_ENCODING
    - Consistent file permissions using FileIoConfig.PERMISSION_MODE
    - Support for Path objects and strings

    Parameters
    ----------
    filename : str | Path
        Path to the file to open.
    mode : {'r', 'w', 'w+', 'x', 'a', 'r+'}
        File opening mode:
        - 'r': Read only
        - 'w': Write (truncate)
        - 'w+': Read/Write (truncate)
        - 'x': Exclusive write (fail if exists)
        - 'a': Append
        - 'r+': Read/Write (no truncate)
    encoding : str or None, optional
        Text encoding. Defaults to FileIoConfig.TEXT_ENCODING if None.

    Returns
    -------
    TextIO
        File stream object for reading/writing.

    Raises
    ------
    FileNotFoundError
        If file doesn't exist in read mode.
    FileExistsError
        If file exists in exclusive write mode ('x').
    PermissionError
        If insufficient permissions to access the file.
    """
    filename_str = str(filename)

    # Map file modes to OS-level flags for secure file handling
    flags_map: dict[str, int] = {
        'r': os.O_RDONLY,
        'w': os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        'w+': os.O_RDWR | os.O_CREAT | os.O_TRUNC,
        'x': os.O_WRONLY | os.O_EXCL | os.O_CREAT,
        'a': os.O_WRONLY | os.O_APPEND | os.O_CREAT,
        'r+': os.O_RDWR | os.O_CREAT,
    }

    flags = flags_map[mode]
    encoding = encoding or FileIoConfig.TEXT_ENCODING

    # Open file with OS-level permissions for security
    file_descriptor = os.open(path=filename_str, flags=flags, mode=FileIoConfig.PERMISSION_MODE)
    return os.fdopen(fd=file_descriptor, mode=mode, encoding=encoding)


# =============================================================================
# JSON File Operations
# =============================================================================

def read_json(
    filename: str | Path,
    encoding: str | None = None,
) -> dict[str, Any]:
    """
    Load JSON data from a file with JSON5 format support.

    This function provides enhanced JSON parsing capabilities:
    - Standard JSON format support
    - JSON5 extensions (comments, trailing commas, unquoted keys, etc.)
    - Automatic encoding handling with BOM support

    Parameters
    ----------
    filename : str | Path
        Path to the JSON file to read.
    encoding : str or None, optional
        Text encoding. Defaults to FileIoConfig.TEXT_ENCODING if None.

    Returns
    -------
    dict[str, Any]
        Parsed JSON data as a dictionary.

    Raises
    ------
    FileNotFoundError
        If the specified file doesn't exist.
    json.JSONDecodeError
        If the file contains invalid JSON/JSON5 syntax.
    """
    with fopen(filename, mode='r', encoding=encoding) as file:
        obj = pyjson5.load(file)
    return obj


def write_json(
    obj: Any,
    filename: str | Path,
    mode: Literal['w', 'a'] = 'w',
    encoding: str | None = None,
    indent: int = 4,
) -> None:
    """
    Serialize an object to a JSON file with pretty formatting.

    Writes data in standard JSON format (not JSON5) with:
    - Unicode characters preserved (ensure_ascii=False)
    - Pretty printing with configurable indentation
    - Automatic conversion of non-serializable objects to strings

    Parameters
    ----------
    obj : Any
        Python object to serialize. Must be JSON-serializable or convertible to str.
    filename : str | Path
        Path to the output JSON file.
    mode : {'w', 'a'}, optional
        Write mode:
        - 'w': Overwrite existing file (default)
        - 'a': Append to existing file
    encoding : str or None, optional
        Text encoding. Defaults to FileIoConfig.TEXT_ENCODING if None.
    indent : int, optional
        Number of spaces for indentation. Defaults to 4.

    Raises
    ------
    TypeError
        If obj contains non-serializable types that can't be converted to str.
    PermissionError
        If insufficient permissions to write to the file.
    """
    with fopen(filename, mode=mode, encoding=encoding) as file:
        json.dump(obj, file, ensure_ascii=False, indent=indent, default=str)

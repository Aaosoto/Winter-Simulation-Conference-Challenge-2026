"""
Data format conversion utilities for O2DES framework.

This module provides functions for converting between different data formats:
- Integer to zero-padded strings
- Timedelta to hours and formatted strings
- Datetime to strings, Unix timestamps, and vice versa
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

__all__ = [
    'normalize_str',
    'int2nstr',
    'td2hrs',
    'td2str',
    'dt2str',
    'dt2unix',
    'dtstr2unix',
    'unix2dt',
]

# =============================================================================
# String Format Conversion
# =============================================================================

def normalize_str(value: str | None) -> str:
    """
    Normalize string input by stripping whitespace.

    Parameters
    ----------
    value : str or None
        String to normalize.

    Returns
    -------
    str
        Normalized string (empty string if None or whitespace-only).

    Raises
    ------
    TypeError
        If value is not a string or None.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"Expected str or None, got {type(value).__name__}")
    return value.strip()


# =============================================================================
# Integer Format Conversion
# =============================================================================

def int2nstr(value: int, length: int) -> str:
    """
    Convert an integer to a zero-padded string with specified length.

    Parameters
    ----------
    value : int
        The integer value to convert.
    length : int
        The expected length of the resulting string.

    Returns
    -------
    str
        The zero-padded string with the specified length.

    Examples
    --------
    >>> int2nstr(42, 5)
    '00042'
    """
    return str(value).zfill(length)


# =============================================================================
# Time Format Conversion
# =============================================================================

def td2hrs(tdiff: dt.timedelta) -> float:
    """
    Convert a timedelta to total hours as a floating-point number.

    Parameters
    ----------
    tdiff : dt.timedelta
        The time difference to convert.

    Returns
    -------
    float
        Total hours as a floating-point number.

    Examples
    --------
    >>> import datetime as dt
    >>> td2hrs(dt.timedelta(days=1, hours=12))
    36.0
    """
    return tdiff.total_seconds() / 3600.0


def td2str(
    tdiff: dt.timedelta,
    td_format: Literal['d day(s) HH:MM:SS', 'HH:MM:SS'] = 'd day(s) HH:MM:SS',
) -> str:
    """
    Convert a timedelta to a formatted string.

    Parameters
    ----------
    tdiff : dt.timedelta
        The time difference to convert.
    td_format : {'d day(s) HH:MM:SS', 'HH:MM:SS'}, optional
        The desired output format. Defaults to 'd day(s) HH:MM:SS'.

    Returns
    -------
    str
        A formatted string representation of the timedelta.

    Raises
    ------
    ValueError
        If the specified format is invalid.

    Examples
    --------
    >>> import datetime as dt
    >>> td2str(dt.timedelta(days=2, hours=3, minutes=15, seconds=30))
    '2 days 03:15:30'
    """
    if td_format == 'd day(s) HH:MM:SS':
        days = tdiff.days
        seconds = tdiff.seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        plural = 's' if abs(days) != 1 else ''
        return f'{days} day{plural} {hours:02d}:{minutes:02d}:{secs:02d}'

    if td_format == 'HH:MM:SS':
        total_seconds = int(tdiff.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f'{hours}:{minutes:02d}:{secs:02d}'

    raise ValueError(f"Invalid format: '{td_format}'. Expected 'd day(s) HH:MM:SS' or 'HH:MM:SS'")


def dt2str(
    dt_obj: dt.datetime,
    dt_format: str = '%Y-%m-%d %H:%M:%S',
) -> str:
    """
    Convert a datetime object to a formatted string.

    Parameters
    ----------
    dt_obj : dt.datetime
        The datetime object to convert.
    dt_format : str, optional
        The desired datetime format string.
        Common formats include:
        - '%Y-%m-%d %H:%M:%S' (default)
        - '%Y-%m-%d %H:%M:%S.%f' (with microseconds)
        - '%Y/%m/%d %H:%M:%S'

    Returns
    -------
    str
        A formatted string representation of the datetime.

    Examples
    --------
    >>> import datetime as dt
    >>> dt_obj = dt.datetime(2023, 11, 8, 15, 30, 45)
    >>> dt2str(dt_obj)
    '2023-11-08 15:30:45'
    """
    return dt_obj.strftime(dt_format)


def dt2unix(dt_obj: dt.datetime) -> int:
    """
    Convert a datetime object to Unix timestamp.

    Unix timestamp is the number of seconds since January 1, 1970, 00:00:00 UTC.

    Parameters
    ----------
    dt_obj : dt.datetime
        The datetime object to convert.

    Returns
    -------
    int
        Unix timestamp in seconds.

    Examples
    --------
    >>> import datetime as dt
    >>> dt_obj = dt.datetime(2023, 11, 8, 12, 0, 0)
    >>> dt2unix(dt_obj)
    1699434000
    """
    return int(dt_obj.timestamp())


def dtstr2unix(dtstr: str, dt_format: str = '%Y%m%d%H%M%S') -> int:
    """
    Convert a datetime string to Unix timestamp.

    Parameters
    ----------
    dtstr : str
        A datetime string in the specified format.
    dt_format : str, optional
        The format of the input datetime string. Defaults to '%Y%m%d%H%M%S'.

    Returns
    -------
    int
        Unix timestamp in seconds.

    Examples
    --------
    >>> dtstr2unix('20231108120000')
    1699434000
    """
    dt_obj = dt.datetime.strptime(dtstr, dt_format)
    return int(dt_obj.timestamp())


def unix2dt(timestamp: float | int) -> dt.datetime:
    """
    Convert Unix timestamp to a datetime object.

    Parameters
    ----------
    timestamp : float | int
        Unix timestamp in seconds (e.g., 1699434000).

    Returns
    -------
    dt.datetime
        A datetime object representing the timestamp.

    Examples
    --------
    >>> unix2dt(1699434000)
    datetime.datetime(2023, 11, 8, 12, 0)
    """
    return dt.datetime.fromtimestamp(timestamp)

"""
O2DES Statistics Module
=======================

Provides logging and statistical tracking utilities for the simulation framework.

Exports
-------
EventLogger
    Sandbox event logging helpers (schedule log, event log).
    Inherits :class:`~o2des.common.Loggable` to own the shared logger and
    output-directory configuration for the whole framework.
"""

from o2des.statistics.event_logger import EventLogger
from o2des.statistics.hour_counter_logger import HourCounterLogger

__all__ = [
    "EventLogger",
    "HourCounterLogger",
]

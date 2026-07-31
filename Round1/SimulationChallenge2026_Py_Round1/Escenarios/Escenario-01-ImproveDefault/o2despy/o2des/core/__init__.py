"""
O2DES - Object-Oriented Discrete-Event Simulation Framework
===========================================================

O2DES is a programming library that implements the modeling and execution of
discrete-event simulation in object-oriented programming paradigm.

Core Components
---------------
- Event: Discrete event with scheduled time and action
- HourCounter: Time-based statistics tracker for numerical variables
- PhaseTracker: Time-based statistics tracker for categorical variables
- Sandbox: Simulation execution environment

Example
-------
>>> from o2des.core import Sandbox, Event
>>> sandbox = Sandbox()
>>> sandbox.run(until=100)
"""

from o2des.core.assets import IAssets
from o2des.core.pointer import Pointer
from o2des.core.event import Event
from o2des.core.hour_counter_base import IHourCounter, IReadOnlyHourCounter
from o2des.core.sandbox_base import ISandbox
from o2des.core.hour_counter import HourCounter, ReadOnlyHourCounter
from o2des.core.phase_tracker import PhaseTracker
from o2des.core.sandbox import Sandbox

__all__ = [
    'IAssets',
    'Pointer',
    'Event',
    'IHourCounter',
    'IReadOnlyHourCounter',
    'ISandbox',
    'HourCounter',
    'ReadOnlyHourCounter',
    'PhaseTracker',
    'Sandbox'
]

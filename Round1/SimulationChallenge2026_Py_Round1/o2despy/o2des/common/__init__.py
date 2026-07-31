"""
O2DES Common Module
===================

Public exports for shared O2DES building blocks.

Exports
-------
ActionSet
    Event action collection utility.
AutoIndexed
    Reusable capability that assigns a sequential unique index to each instance.
IDisposable
    Disposable interface.
Loggable
    Reusable capability for shared logging support.
"""

from o2des.common.actionset import ActionSet
from o2des.common.auto_indexed import AutoIndexed
from o2des.common.disposable_base import IDisposable
from o2des.common.loggable import Loggable

__all__ = [
    'ActionSet',
    'AutoIndexed',
    'IDisposable',
    'Loggable',
]

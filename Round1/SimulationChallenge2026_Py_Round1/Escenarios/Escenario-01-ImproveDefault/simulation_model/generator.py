"""
Base Generator class for O2DES Python port.

Mirrors O2DES.Generator<T> - a Sandbox subclass that generates
entities on a schedule and exposes them through the arrive() method.
"""

from __future__ import annotations

import sys
from typing import Generic, TypeVar

from o2des.common import ActionSet
from o2des.core import Sandbox

T = TypeVar('T')


class Generator(Sandbox, Generic[T]):
    """
    Base generator class that creates entities on a schedule.

    Generator<T> is a Sandbox subclass that manages the creation and
    introduction of entities into the simulation. Entities are created
    through the Generate() method and introduced via arrive().
    """

    def __init__(
        self,
        id: str = "",
        seed: int = 0
    ):
        uid = id if id else self.__class__.__name__
        super().__init__(seed=seed, uid=uid)

        # OnArrive: event raised when a load arrives from this generator.
        # Wired to downstream Activity's signal_start in Model._connect_event_flow.
        self.on_arrive = ActionSet(object)

        # on_finish: alias of OnArrive, used by Model._connect_event_flow for wiring.
        # Reference Generator<T>.on_arrive is wired via ConnectTo() which calls next.RequestStart(),
        # but Model._connect_event_flow() expects on_finish on all event sources.
        self.on_finish = self.on_arrive

    def arrive(self, entity: T) -> None:
        """
        Raise the arrival event for a generated load.

        Reference: arrive(TLoad load) calls OnArrive.Each(action => action?.Invoke(load))
        """
        # self._log("Generate", entity)
        self.on_arrive(entity)

    def _log(self, event_name: str, entity: T = None) -> None:
        """Print a timestamped log message (mirrors the reference behavior Generator.Log)."""
        # Reference log format: "[d\.hh\:mm\:ss] {Id} | {eventName}" + optional entity
        time_str = self._clock_time.strftime("%d.%H:%M:%S")
        entity_str = f" | {entity}" if entity is not None else ""
        print(f"[{time_str}] {self.uid} | {event_name}{entity_str}", file=sys.stdout)
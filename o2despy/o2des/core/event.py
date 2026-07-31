from __future__ import annotations

import datetime as dt
from functools import total_ordering
from typing import TYPE_CHECKING

from o2des.common import AutoIndexed, IDisposable

if TYPE_CHECKING:
    from collections.abc import Callable

    from o2des.core import ISandbox


@total_ordering
class Event(AutoIndexed, IDisposable):
    """
    Represents a scheduled event in the simulation.

    An event has the following features:
    - it is scheduled by a Sandbox object;
    - it will be invoked at a future time;
    - it contains a callable object (called an action);
    - the related callable object will be called when the event is invoked.
    """

    def __init__(
        self,
        owner: ISandbox,
        action: Callable,
        scheduled_time: dt.datetime,
        tag: str | None = None,
    ) -> None:
        """
        Initialize with the information of a specified event.

        The key information of an event mainly includes:
        - the callable object related to the event,
        - the future time to invoke the event, and
        - the owner of the event, i.e. the Sandbox instance that schedules the event.

        Parameters
        ----------
        owner : ISandbox
            Sandbox instance that schedules the event.
        action : Callable
            A callable object related to the event, which will be called when the event is invoked.
        scheduled_time : dt.datetime
            Future time when the event will be invoked.
        tag : str | None, optional
            Tag associated with the event, if any.
        """
        super().__init__()
        self._owner: ISandbox = owner
        self._action: Callable = action
        self._scheduled_time: dt.datetime = scheduled_time
        self._tag: str | None = tag

    def __str__(self) -> str:
        return f"{self._tag or self.__class__.__name__}#{self._index}"

    def __repr__(self) -> str:
        return f"{self._tag or self.__class__.__name__}#{self._index}"

    def __hash__(self) -> int:
        """
        Hash value for the Event instance based on its index.
        """
        return hash(self._index)

    def __eq__(self, other: Event) -> bool:
        """
        Compare this Event object and another Event object by their scheduled time and index.

        Parameters
        ----------
        other : Event
            Another Event object to compare with.

        Returns
        -------
        bool
            Whether these two Event objects are equal.

        Raises
        ------
        TypeError
            If the type of the other object is not Event.
        """
        if not isinstance(other, Event):
            raise TypeError(f"expect type of 'Event' but got {type(other)}.")

        is_equal = (
            self._scheduled_time == other._scheduled_time
            and self._index == other._index
        )
        return is_equal

    def __lt__(self, other: Event) -> bool:
        """
        Compare this Event object and another Event object by their scheduled time and index.

        Parameters
        ----------
        other : Event
            Another Event object to compare with.

        Returns
        -------
        bool
            Whether this Event object is less than another one.

        Raises
        ------
        TypeError
            If the type of the other object is not Event.
        """
        if not isinstance(other, Event):
            raise TypeError(f"expect type of 'Event' but got {type(other)}.")

        if self._scheduled_time == other.scheduled_time:
            return self._index < other.index
        else:
            return self._scheduled_time < other.scheduled_time

    @property
    def owner(self) -> ISandbox:
        """
        Sandbox object that schedules this event.
        """
        return self._owner

    @property
    def action(self) -> Callable:
        """
        A callable object related to the event, which will be called when the event is invoked.
        """
        return self._action

    @property
    def scheduled_time(self) -> dt.datetime:
        """
        Future time when the event will be invoked.
        """
        return self._scheduled_time

    @property
    def tag(self) -> str | None:
        """
        Tag associated with the event, if any.
        """
        return self._tag

    def invoke(self) -> None:
        """
        Invoke the event, i.e. call corresponding callable object.
        """
        self._action()

    def dispose(self) -> None:
        super().dispose()

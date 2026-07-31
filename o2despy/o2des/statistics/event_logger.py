"""
Logging helpers for the Sandbox simulation component.

All logic is grouped under :class:`EventLogger` as static methods.  By
inheriting :class:`~o2des.common.Loggable`, ``EventLogger`` owns the shared
logger and output-directory configuration for the whole framework — no other
class needs to inherit ``Loggable`` solely for logging access.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from o2des.common import Loggable

if TYPE_CHECKING:
    from o2des.core import Event, Sandbox

SIM_TIME_FORMAT = "%a %Y-%m-%d %H:%M:%S.%f"


class EventLogger(Loggable):
    """
    Namespace for sandbox event logging helpers.

    Inherits :class:`~o2des.common.Loggable` to own the shared logger and
    output-directory configuration.  All logging methods are static — no
    instance is needed.
    """

    @classmethod
    def schedule_log(
        cls,
        clock_time: dt.datetime,
        future_event: Event,
    ) -> None:
        """
        Record a log entry when an event is added to the future event list.

        Parameters
        ----------
        clock_time : dt.datetime
            Current simulation clock time at the moment of scheduling.
        future_event : Event
            The event that was just scheduled.
        """
        logger = cls.get_logger()
        if logger is None:
            return

        # Extract function details from a potentially wrapped partial
        func, args, kwargs = future_event.action, (), {}
        if hasattr(func, "func"):
            kwargs = {k: str(v) for k, v in func.keywords.items()}
            args = tuple(str(arg) for arg in func.args)
            func = func.func

        # Build fully-qualified event name
        event_name = (
            f"{func.__self__}.{func.__name__}"
            if hasattr(func, "__self__")
            else func.__name__
        )

        msg = (
            "{[[sim_time]]:" + f"{SIM_TIME_FORMAT}" + "} | "
            "{[[owner]]} scheduled {[[event]]} @ {[[scheduled_time]]:" + f"{SIM_TIME_FORMAT}" + "}"
            ", args: {args}, {kwargs}"
        )

        logger.opt(
            record=True,
            depth=2,
        ).bind(
            output_tag="schedule",
            sim_time=clock_time,
            owner=str(future_event.owner),
            event=event_name,
            scheduled_time=future_event.scheduled_time,
        ).info(msg, args=args, kwargs=kwargs)

    @classmethod
    def event_log(
        cls,
        clock_time: dt.datetime,
        owner: Sandbox,
        msg: str | None = None,
        include_sim_time: bool = True,
        include_event_info: bool = False,
        trigger: object | str | None = None,
        level: str = "INFO",
        depth: int = 0,
        **extra: Any,
    ) -> None:
        """
        Record a simulation log entry.

        Parameters
        ----------
        clock_time : dt.datetime
            Current simulation clock time.
        owner : Sandbox
            The owning sandbox instance.
        msg : str or None, optional
            Log message template with placeholder support. Defaults to None.
        include_sim_time : bool, optional
            Prepend current simulation time to the message. Defaults to True.
        include_event_info : bool, optional
            Prepend owner and function name to the message. Defaults to False.
        trigger : object or str or None, optional
            Object that triggered the log entry. Defaults to None.
        level : str, optional
            Log severity level. Defaults to ``"INFO"``.
        depth : int, optional
            Additional call-stack frames to skip for accurate source location.
            Defaults to 0.
        **extra : Any
            Additional context variables interpolated into the log message.
        """
        logger = cls.get_logger()
        if logger is None:
            return

        msg = msg if msg else ""

        time_info = ""
        if include_sim_time:
            time_info = "{[[sim_time]]:" + f"{SIM_TIME_FORMAT}" + "} | "

        event_info = ""
        if trigger:
            event_info += f"{trigger} triggered "
            event_info += "{[[owner]]}.{[function]}"
            if msg:
                event_info += " | "
        elif include_event_info:
            event_info += "{[[owner]]}.{[function]}"
            if msg:
                event_info += " | "
        else:
            if not msg:
                return  # Nothing to log

        formatted_msg = time_info + event_info + msg

        logger.opt(
            record=True,
            depth=depth,
        ).bind(
            output_tag="trigger",
            sim_time=clock_time,
            owner=str(owner),
        ).log(level, formatted_msg, **extra)

    @classmethod
    def log_debug(cls, msg: str, *args: Any, **kwargs: Any) -> None:
        logger = cls.get_logger()
        if logger is None:
            return
        logger.debug(msg, *args, **kwargs)

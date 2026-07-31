from __future__ import annotations

import datetime as dt
from functools import partial
from typing import Any, TypeVar, TYPE_CHECKING

import numpy as np
from sortedcontainers import SortedSet

from o2des.common import ActionSet, AutoIndexed
from o2des.core import Event, HourCounter, ISandbox, PhaseTracker
from o2des.utils import FormatUtils
from o2des.utils.dotnet_random import DotNetRandom

if TYPE_CHECKING:
    from collections.abc import Callable

_S = TypeVar('_S', bound='Sandbox')


class Sandbox(AutoIndexed, ISandbox):
    """
    Discrete-event simulation sandbox for managing and executing future events.

    This class serves as the fundamental component of the O2DES framework,
    implementing event scheduling, execution, and hierarchical simulation
    management. It maintains a future event list and processes events in
    chronological order to update system state.

    The sandbox operates hierarchically, where each instance can have a parent
    and multiple children, enabling modular simulation design. Events are
    scheduled with specific times and executed according to their priority.

    Random number generation
    ------------------------
    Each sandbox owns a `DotNetRandom` instance accessible via `self._default_rs`.
    This is a pure-Python re-implementation of C#'s `System.Random` (Knuth
    subtractive PRNG), so the Python port produces byte-identical stochastic
    output to the C# / O2DESNet implementation given the same seed.

    Sub-sandbox sharing semantics: a child sandbox added via `add_child`
    shares its parent's `_default_rs` by reference (matching C# O2DESNet's
    default behaviour). Calling `child.seed = N` after the child is added
    will instantiate a fresh `DotNetRandom` for the child only.

    Methods available on `self._default_rs`:
        - `next()` -> int         : in [0, 2^31 - 1)
        - `next_double()` -> float: in [0, 1.0)
        - `next_max(n)` -> int    : in [0, n)
        - `random()` / `integers(lo, hi)`: numpy-style aliases

    The `np.random.Generator` API is **not** available on `_default_rs`.
    If you need numpy-style sampling, construct your own
    `np.random.default_rng(seed)` and store it on a separate attribute.

    Examples
    --------
    >>> sandbox = Sandbox(seed=42, uid="MySimulation")
    >>> sandbox.schedule(my_event_handler, dt.timedelta(hours=1))
    >>> sandbox.run(duration=dt.timedelta(days=7))
    """

    def __init__(
        self,
        seed: int = 0,
        uid: str | None = None,
    ) -> None:
        """
        Initialize with the optional random seed and uid.
        
        Parameters
        ----------
        seed : int, optional
            Seed value used for reproducible random number generation. Defaults to 0.
        uid : str or None, optional
            Tag of the instance of the module.

        Raises
        ------
        TypeError
            If `uid` is not a string or None.
        """
        super().__init__()
        self._uid: str = FormatUtils.normalize_str(uid)

        # Random number generation - Foundation for stochastic simulation
        # DefaultRS is a DotNetRandom (re-implementation of C# System.Random)
        # so that the Python port produces byte-identical stochastic output
        # to the C# / O2DESNet implementation.
        # For child sandboxes (parent is not None), the parent's RNG is
        # shared by reference — mirroring C# O2DESNet's sharing semantics.
        self._seed: int = 0
        self._default_rs: "DotNetRandom | None" = None
        self.seed = seed  # Initialize via setter to trigger RNG setup

        # Configuration - Runtime behavior control
        self._debug_mode: bool = False

        # Simulation state - Core temporal and event tracking
        self._clock_time: dt.datetime = dt.datetime.min
        self._future_event_list: SortedSet[Event] = SortedSet()
        self._real_time_for_last_run: dt.datetime | None = None

        # Hierarchical structure - Parent-child simulation composition
        self._parent: Sandbox | None = None
        self._children: list[Sandbox] = []

        # Statistics and tracking - Performance measurement components
        self._hour_counters: list[HourCounter] = []
        self._phase_trackers: list[PhaseTracker] = []

        # Event callbacks - Lifecycle event handlers
        self._on_warmup: ActionSet = ActionSet().add(self._warmup_handler)

        # Event logging - Hook for recording scheduled events
        self.on_event_scheduled: ActionSet = ActionSet(dt.datetime, Event)

    # -------------------------------------------------------------------------
    # Properties - Identity
    # -------------------------------------------------------------------------

    @property
    def uid(self) -> str:
        """
        Tag of the instance of the module.
        """
        return self._uid

    def __str__(self) -> str:
        return f"{self._uid or self.__class__.__name__}#{self.index}"

    def __repr__(self) -> str:
        return f"{self._uid or self.__class__.__name__}#{self.index}"

    # -------------------------------------------------------------------------
    # Properties - Configuration
    # -------------------------------------------------------------------------

    @property
    def seed(self) -> int:
        """
        Random seed for reproducible number generation.
        Setting the seed reinitializes the random number generator.
        """
        return self._seed

    @seed.setter
    def seed(self, value: int) -> None:
        self._seed = value
        # Note: when this setter runs from __init__, `_parent` may not yet
        # exist as an instance attribute (it is only created when the child
        # is later added to a parent). We use getattr with a None default
        # to treat that case as "no parent" → root behaviour.
        parent = getattr(self, "_parent", None)
        if parent is None:
            # Root sandbox: instantiate a fresh RNG from the seed.
            self._default_rs = DotNetRandom(value)
        else:
            # Child sandbox: share the parent's RNG by reference, matching
            # C# O2DESNet's default behaviour (sub-sandbox DefaultRS is the
            # same instance as the parent's).
            self._default_rs = parent._default_rs

    @property
    def debug_mode(self) -> bool:
        """
        Debug mode status. True if debug mode is enabled.
        """
        return self._debug_mode

    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        self._debug_mode = value

    # -------------------------------------------------------------------------
    # Properties - Hierarchical Structure
    # -------------------------------------------------------------------------

    @property
    def parent(self) -> Sandbox | None:
        """
        Parent sandbox in the hierarchy, or None if this is a root node.
        """
        return self._parent

    @parent.setter
    def parent(self, value: Sandbox) -> None:
        self._parent = value

    @property
    def children(self) -> tuple[Sandbox, ...]:
        """
        Immutable tuple of child nodes linked to this sandbox.
        """
        return tuple(self._children)

    # -------------------------------------------------------------------------
    # Properties - Statistics and Tracking
    # -------------------------------------------------------------------------

    @property
    def hour_counters(self) -> tuple[HourCounter, ...]:
        """
        Immutable tuple of hour counters for time-based statistics.
        """
        return tuple(self._hour_counters)

    @property
    def phase_trackers(self) -> tuple[PhaseTracker, ...]:
        """
        Immutable tuple of phase trackers for state transition monitoring.
        """
        return tuple(self._phase_trackers)

    # -------------------------------------------------------------------------
    # Properties - Event Callbacks
    # -------------------------------------------------------------------------

    @property
    def on_warmup(self) -> ActionSet:
        """
        Action set executed upon warmup completion.
        """
        return self._on_warmup

    @on_warmup.setter
    def on_warmup(self, value: ActionSet) -> None:
        self._on_warmup = value

    # -------------------------------------------------------------------------
    # Properties - Simulation State
    # -------------------------------------------------------------------------

    @property
    def clock_time(self) -> dt.datetime:
        """
        Current simulation time. Delegates to parent if hierarchical.
        """
        if self._parent is None:
            return self._clock_time
        return self._parent.clock_time

    @property
    def future_event_list(self) -> SortedSet[Event]:
        """
        Sorted set of all scheduled future events.
        """
        return self._future_event_list

    @property
    def head_event(self) -> Event | None:
        """
        Event with the earliest scheduled time across this sandbox and children.

        Returns None if no events are scheduled.
        """
        event: Event | None = None
        if self._future_event_list:
            event = self._future_event_list[0]

        # Check all children for earlier events
        for child in self._children:
            child_head_event = child.head_event
            if event is None or (child_head_event and child_head_event < event):
                event = child_head_event

        return event

    @property
    def head_event_time(self) -> dt.datetime | None:
        """
        Scheduled time of the earliest event, or None if queue is empty.
        """
        head = self.head_event
        return head.scheduled_time if head else None

    # -------------------------------------------------------------------------
    # Hierarchical Management
    # -------------------------------------------------------------------------

    def add_child(self, child: _S) -> _S:
        """
        Add a child sandbox to create hierarchical simulation structure.

        Automatically establishes parent-child relationship and synchronizes
        warmup callbacks.

        Parameters
        ----------
        child : _S
            Child sandbox to add to the hierarchy. Must be a subclass of Sandbox.

        Returns
        -------
        _S
            The added child sandbox for method chaining, preserving its concrete type.
        """
        # Set _parent BEFORE assigning child.parent so that any future code
        # that introspects _parent (e.g. the seed setter) sees the link.
        child._parent = self
        child.parent = self
        # C# O2DESNet: each child keeps its OWN Random(seed), NOT the parent's.
        # The child's __init__ already created DotNetRandom(seed) from the seed
        # value passed in. Do NOT overwrite it. (Python used to rebind to
        # parent's RNG here, but that was wrong — it made all children share
        # the same RNG, diverging from C# behavior.)
        self._children.append(child)
        self._on_warmup.add(child.on_warmup)
        return child

    # -------------------------------------------------------------------------
    # Statistics Components
    # -------------------------------------------------------------------------

    def add_hour_counter(
        self,
        keep_history: bool = False,
    ) -> HourCounter:
        """
        Create and register an hour counter for time-based statistics.

        Parameters
        ----------
        keep_history : bool, optional
            Whether to keep full history of each observation. Defaults to False.

        Returns
        -------
        HourCounter
            Newly created and registered hour counter.
        """
        hc = HourCounter(self, keep_history=keep_history)
        self._hour_counters.append(hc)
        self._on_warmup.add(hc.warmup)
        return hc

    def add_phase_tracker(
        self,
        initial_state: str,
        history_on: bool = False,
    ) -> PhaseTracker:
        """
        Create and register a phase tracker for state transition monitoring.

        Parameters
        ----------
        initial_state : str
            Initial state value at simulation start.
        history_on : bool, optional
            Whether to keep full history of state changes. Defaults to False.

        Returns
        -------
        PhaseTracker
            Newly created and registered phase tracker.
        """
        tracker = PhaseTracker(self, initial_state, history_on=history_on)
        self._on_warmup.add(tracker.warmup)
        self._phase_trackers.append(tracker)
        return tracker

    # -------------------------------------------------------------------------
    # Event Scheduling
    # -------------------------------------------------------------------------

    def schedule(
        self,
        action: Callable[..., Any],
        clock_time: dt.datetime | None = None,
        delay: dt.timedelta | None = None,
        tag: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Schedule an event for future execution.

        The event can be scheduled either by absolute `clock_time`
        or by relative `delay` from current clock time.
        If both are omitted, the event is scheduled at current clock time.

        Parameters
        ----------
        action : Callable[..., Any]
            Callable to execute when the event triggers.
        clock_time : dt.datetime | None, optional
            Absolute clock time for event execution.
        delay : dt.timedelta | None, optional
            Relative delay from current clock time.
        tag : str | None, default=None
            Optional identifier for event logging and tracking.
        *args : Any
            Positional arguments passed to the action.
        **kwargs : Any
            Keyword arguments passed to the action.

        Raises
        ------
        TypeError
            If `action` is not callable, or `clock_time`/`delay` has invalid type.
        ValueError
            If both `clock_time` and `delay` are provided.

        Examples
        --------
        >>> # Schedule immediately at current clock time
        >>> sandbox.schedule(process_order, order_id=123)
        >>> # Schedule with relative delay
        >>> sandbox.schedule(process_order, delay=dt.timedelta(hours=1), order_id=123)
        >>> # Schedule at absolute time
        >>> sandbox.schedule(close_shop, clock_time=dt.datetime(2025, 11, 12, 18, 0))
        """
        if not callable(action):
            raise TypeError("'action' must be callable")

        if clock_time is not None and delay is not None:
            raise ValueError("'clock_time' and 'delay' cannot both be provided")

        if clock_time is not None and not isinstance(clock_time, dt.datetime):
            raise TypeError(f"'clock_time' must be dt.datetime or None, got {type(clock_time).__name__}")
        if delay is not None and not isinstance(delay, dt.timedelta):
            raise TypeError(f"'delay' must be dt.timedelta or None, got {type(delay).__name__}")

        if clock_time is not None:
            scheduled_time = clock_time
        elif delay is not None:
            scheduled_time = self.clock_time + delay
        else:
            scheduled_time = self.clock_time

        # Create and enqueue event
        future_event = Event(
            owner=self,
            action=partial(action, *args, **kwargs),
            scheduled_time=scheduled_time,
            tag=tag,
        )
        self._future_event_list.add(future_event)
        self.on_event_scheduled.invoke(scheduled_time, future_event)

    # -------------------------------------------------------------------------
    # Event Execution
    # -------------------------------------------------------------------------

    def run_all(self) -> None:
        """
        Execute all scheduled events until the queue is exhausted.
        """
        while self.run_once():
            pass

    def run(self, **kwargs: Any) -> bool:
        """
        Run simulation until a specified condition is satisfied.

        Supports multiple execution modes controlled by keyword arguments.
        Priority order: terminate > duration > event_count > speed.
        If no arguments provided, executes single event.

        Parameters
        ----------
        **kwargs : Any
            Execution control parameters:
            - terminate (dt.datetime): Run until specified clock time
            - duration (dt.timedelta): Run for specified duration
            - event_count (int): Execute N events
            - speed (float): Real-time speed multiplier

        Returns
        -------
        bool
            True if more events remain, False if queue is empty.

        Raises
        ------
        ValueError
            If no valid keyword argument provided.

        Examples
        --------
        >>> sandbox.run(terminate=dt.datetime(2025, 12, 31))
        >>> sandbox.run(duration=dt.timedelta(hours=24))
        >>> sandbox.run(event_count=100)
        >>> sandbox.run(speed=2.0)  # 2x real-time
        >>> sandbox.run()  # Single event
        """
        if not kwargs:
            return self.run_once()
        if "terminate" in kwargs:
            return self.run_until(kwargs["terminate"])
        if "duration" in kwargs:
            return self.run_for_period(kwargs["duration"])
        if "event_count" in kwargs:
            return self.run_multiple_times(kwargs["event_count"])
        if "speed" in kwargs:
            return self.run_at_speed(kwargs["speed"])
        raise ValueError(f"Invalid keyword arguments: {kwargs}")

    def run_once(self) -> bool:
        """
        Execute the single earliest event.

        Returns
        -------
        bool
            True if more events remain, False if queue is empty.
        """
        if self._parent is not None:
            return self._parent.run_once()

        head = self.head_event
        if head is None:
            return False

        head.owner.future_event_list.discard(head)
        self._clock_time = head.scheduled_time
        head.invoke()
        return True

    def run_until(self, terminate: dt.datetime) -> bool:
        """
        Run simulation until specified clock time is reached.

        Parameters
        ----------
        terminate : dt.datetime
            Target clock time to stop simulation.

        Returns
        -------
        bool
            True if more events remain beyond termination time, False otherwise.
        """
        if self._parent is not None:
            return self._parent.run_until(terminate)

        while True:
            head = self.head_event
            if head is not None and head.scheduled_time <= terminate:
                self.run_once()
            else:
                self._clock_time = terminate
                return head is not None

    def run_for_period(self, duration: dt.timedelta) -> bool:
        """
        Run simulation for specified time duration.

        Parameters
        ----------
        duration : dt.timedelta
            Time duration to advance simulation.

        Returns
        -------
        bool
            True if more events remain, False otherwise.
        """
        if self._parent is not None:
            return self._parent.run_for_period(duration)
        return self.run_until(terminate=self.clock_time + duration)

    def run_multiple_times(self, event_count: int) -> bool:
        """
        Execute specified number of events.

        Parameters
        ----------
        event_count : int
            Number of events to execute. Must be positive.

        Returns
        -------
        bool
            True if more events remain, False if queue emptied early.
        """
        if self._parent is not None:
            return self._parent.run_multiple_times(event_count)

        for _ in range(event_count):
            if not self.run_once():
                return False
        return True

    def run_at_speed(self, speed: float) -> bool:
        """
        Run simulation at specified real-time speed multiplier.

        The simulation advances by `speed * elapsed_cpu_time`, where
        `elapsed_cpu_time` is the wall-clock time since the last invocation.

        Parameters
        ----------
        speed : float
            Real-time speed multiplier. Must be positive.
            - speed = 1.0: Real-time (1s CPU = 1s simulation)
            - speed > 1.0: Faster than real-time
            - speed < 1.0: Slower than real-time

        Returns
        -------
        bool
            True if more events remain, False otherwise.

        Examples
        --------
        >>> # Run at 2x speed: 1 second CPU time = 2 seconds simulation time
        >>> sandbox.run_at_speed(2.0)
        """
        if self._parent is not None:
            return self._parent.run_at_speed(speed)

        result = True
        if self._real_time_for_last_run is not None:
            elapsed = dt.datetime.now() - self._real_time_for_last_run
            duration = dt.timedelta(seconds=elapsed.total_seconds() * speed)
            result = self.run(terminate=self.clock_time + duration)

        self._real_time_for_last_run = dt.datetime.now()
        return result

    # -------------------------------------------------------------------------
    # Warmup Phase
    # -------------------------------------------------------------------------

    def warmup(self, **kwargs: Any) -> bool:
        """
        Execute warmup phase to reach steady state before data collection.

        The warmup phase runs the simulation without collecting statistics,
        allowing the system to reach equilibrium before formal data collection
        begins. This is particularly useful for removing initialization bias.

        This method accepts keyword arguments to control execution:
        - `till` (dt.datetime): Warm up until specified clock time
        - `period` (dt.timedelta): Warm up for specified duration

        Parameters
        ----------
        **kwargs : Any
            Warmup control parameters:
            - till (dt.datetime): Warm up until specified time
            - period (dt.timedelta): Warm up for specified duration

        Returns
        -------
        bool
            True if more events remain after warmup, False otherwise.

        Raises
        ------
        ValueError
            If no valid keyword argument provided.

        Examples
        --------
        >>> sandbox.warmup(till=dt.datetime(2025, 1, 1))
        >>> sandbox.warmup(period=dt.timedelta(days=7))
        """
        if "till" in kwargs:
            return self.warmup_until(kwargs["till"])
        if "period" in kwargs:
            return self.warmup_for_period(kwargs["period"])
        raise ValueError("Expected 'till' or 'period' keyword argument")

    def warmup_until(self, till: dt.datetime) -> bool:
        """
        Warm up simulation until specified clock time.

        Parameters
        ----------
        till : dt.datetime
            Target clock time to end warmup phase.

        Returns
        -------
        bool
            True if more events remain, False otherwise.
        """
        if self._parent is not None:
            return self._parent.warmup_until(till)

        result = self.run(terminate=till)
        self._on_warmup.invoke()
        return result

    def warmup_for_period(self, period: dt.timedelta) -> bool:
        """
        Warm up simulation for specified time duration.

        Parameters
        ----------
        period : dt.timedelta
            Duration of warmup phase.

        Returns
        -------
        bool
            True if more events remain, False otherwise.
        """
        if self._parent is not None:
            return self._parent.warmup_for_period(period)
        return self.warmup_until(till=self.clock_time + period)

    def _warmup_handler(self) -> None:
        """
        Handle warmup completion event.

        Override in subclasses to implement custom warmup completion logic.
        """
        pass

    # -------------------------------------------------------------------------
    # Disposal
    # -------------------------------------------------------------------------

    def dispose(self) -> None:
        """
        Disposal of the object, releasing any resources or performing cleanup as needed.

        This method recursively disposes all children and statistics components.
        """
        super().dispose()
        for child in self._children:
            child.dispose()
        for hc in self._hour_counters:
            hc.dispose()
        for pt in self._phase_trackers:
            pt.dispose()

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def rand_seed(self) -> int:
        """
        Generate a random integer.

        Returns
        -------
        int
            A random integer.
        """
        return self._default_rs.next_max(int(1e9))

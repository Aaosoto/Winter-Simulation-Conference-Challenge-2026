from __future__ import annotations

import datetime as dt
from abc import abstractmethod

from o2des.common import IDisposable


class ISandbox(IDisposable):
    """
    Interface for O2DES discrete-event simulation sandbox.

    Defines the contract for event scheduling, hierarchical composition,
    and simulation execution. Concrete implementations must satisfy all
    abstract properties and methods.
    """

    # =========================================================================
    # Properties - Identity
    # =========================================================================

    @property
    @abstractmethod
    def index(self) -> int:
        """
        Read-only unique index in sequence for all instances of the module.
        """
        ...

    @property
    @abstractmethod
    def uid(self) -> str:
        """
        Tag of the instance of the module.
        """
        ...

    # =========================================================================
    # Properties - Configuration
    # =========================================================================

    @property
    @abstractmethod
    def seed(self) -> int:
        """
        Random seed for reproducible number generation.
        """
        ...

    @property
    @abstractmethod
    def debug_mode(self) -> bool:
        """
        Debug mode status. True if debug mode is enabled, False otherwise.
        """
        ...

    # =========================================================================
    # Properties - Hierarchical Structure
    # =========================================================================

    @property
    @abstractmethod
    def parent(self) -> ISandbox | None:
        """
        Parent sandbox in the hierarchy, or None if this is a root node.
        """
        ...

    @property
    @abstractmethod
    def children(self) -> tuple[ISandbox, ...]:
        """
        Immutable tuple of child nodes linked to this sandbox.
        """
        ...

    # =========================================================================
    # Properties - Simulation State
    # =========================================================================

    @property
    @abstractmethod
    def clock_time(self) -> dt.datetime:
        """
        Current simulation time. Delegates to parent if hierarchical.
        """
        ...

    @property
    @abstractmethod
    def head_event_time(self) -> dt.datetime | None:
        """
        Scheduled time of the earliest future event, or None if event queue is empty.
        """
        ...

    # =========================================================================
    # Event Execution
    # =========================================================================

    @abstractmethod
    def run(self, **kwargs) -> bool:
        """
        Run simulation until a specified condition is satisfied.

        This method accepts various keyword arguments to control the simulation
        execution. Arguments are checked in the following priority order:
        - `terminate` (dt.datetime): Run until specified clock time
        - `duration` (dt.timedelta): Run for specified time duration
        - `event_count` (int): Execute specified number of events
        - `speed` (float): Run at real-time speed multiplier

        If no arguments are provided, executes the earliest single event.

        Parameters
        ----------
        **kwargs : dt.datetime | dt.timedelta | int | float
            Keyword arguments specifying the run condition.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.

        Examples
        --------
        >>> sandbox.run(terminate=dt.datetime(2025, 12, 31))
        >>> sandbox.run(duration=dt.timedelta(hours=24))
        >>> sandbox.run(event_count=100)
        >>> sandbox.run(speed=2.0)
        >>> sandbox.run()  # Execute single event
        """
        ...

    @abstractmethod
    def run_once(self) -> bool:
        """
        Execute the earliest single event.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.
        """
        ...

    @abstractmethod
    def run_until(self, terminate: dt.datetime) -> bool:
        """
        Run simulation until specified clock time.

        Parameters
        ----------
        terminate : dt.datetime
            Target clock time at which to stop the simulation.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.

        Raises
        ------
        ValueError
            If `terminate` is before the current `clock_time`.
        """
        ...

    @abstractmethod
    def run_for_period(self, duration: dt.timedelta) -> bool:
        """
        Run simulation for specified time duration.

        Parameters
        ----------
        duration : dt.timedelta
            Time duration for which to run the simulation.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.

        Raises
        ------
        ValueError
            If `duration` is negative.
        """
        ...

    @abstractmethod
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
            True if simulation can continue (more events available),
            False otherwise.

        Raises
        ------
        ValueError
            If `event_count` is not positive.
        """
        ...

    @abstractmethod
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
            True if simulation can continue (more events available),
            False otherwise.

        Raises
        ------
        ValueError
            If `speed` is not positive.

        Examples
        --------
        >>> # Run at 2x speed: 1 second CPU time = 2 seconds simulation time
        >>> sandbox.run_at_speed(2.0)
        >>> # Run at half speed: 2 seconds CPU time = 1 second simulation time
        >>> sandbox.run_at_speed(0.5)
        """
        ...

    # =========================================================================
    # Warmup Phase
    # =========================================================================

    @abstractmethod
    def warmup(self, **kwargs) -> bool:
        """
        Warm up simulation to reach steady state.

        The warmup phase runs the simulation without collecting statistics,
        allowing the system to reach equilibrium before formal data collection
        begins. This is particularly useful for removing initialization bias.

        This method accepts various keyword arguments to control the simulation
        execution. Arguments are checked in the following priority order:
        - `till` (dt.datetime): Warm up until specified clock time
        - `period` (dt.timedelta): Warm up for specified duration

        Parameters
        ----------
        **kwargs : dt.datetime | dt.timedelta
            Keyword arguments specifying the warmup condition.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.

        Examples
        --------
        >>> sandbox.warmup(till=dt.datetime(2025, 1, 1))
        >>> sandbox.warmup(period=dt.timedelta(days=7))
        """
        ...

    @abstractmethod
    def warmup_until(self, till: dt.datetime) -> bool:
        """
        Warm up simulation until specified clock time.

        Parameters
        ----------
        till : datetime
            Target clock time at which to stop the warmup phase.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.

        Raises
        ------
        ValueError
            If `till` is before the current `clock_time`.
        """
        ...

    @abstractmethod
    def warmup_for_period(self, period: dt.timedelta) -> bool:
        """
        Warm up simulation for specified time duration.

        Parameters
        ----------
        period : dt.timedelta
            Time duration for the warmup phase.

        Returns
        -------
        bool
            True if simulation can continue (more events available),
            False otherwise.

        Raises
        ------
        ValueError
            If `period` is negative.
        """
        ...

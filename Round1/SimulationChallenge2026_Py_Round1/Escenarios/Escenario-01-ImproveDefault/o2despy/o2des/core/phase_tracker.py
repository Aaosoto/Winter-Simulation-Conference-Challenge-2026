from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from o2des.common import AutoIndexed, IDisposable
from o2des.utils import FormatUtils

if TYPE_CHECKING:
    from o2des.core import ISandbox


# =============================================================================
# Phase Tracker
# =============================================================================

class PhaseTracker(AutoIndexed, IDisposable):
    """
    Time-series tracker for tracking phase variables.

    This class monitors and records state transitions of a categorical variable,
    maintaining statistics about time spent in each phase and optionally keeping
    a complete history of transitions.
    """

    def __init__(
        self,
        sandbox: ISandbox,
        initial_phase: str,
        initial_time: dt.datetime | None = None,
        history_on: bool = False,
    ) -> None:
        """
        Initialize a phase tracker for the specified sandbox.

        Parameters
        ----------
        sandbox : ISandbox
            The owning sandbox instance.
        initial_phase : str
            Initial phase value at creation.
        initial_time : dt.datetime | None, optional
            Initial time. Defaults to the sandbox's current clock time if not provided.
        history_on : bool, optional
            Whether to record a complete history of transitions. Defaults to False.
        """
        super().__init__()
        self._sandbox: ISandbox = sandbox

        # Time tracking
        self._initial_time: dt.datetime = initial_time or self._sandbox.clock_time
        self._last_time: dt.datetime = self._initial_time

        # State variables
        self._last_phase: str = initial_phase

        # Statistical accumulators
        self._total_hours: float = 0.0
        self._phase2hours: dict[str, float] = {}

        # Observation history
        self._history_on: bool = history_on
        self._history: list[tuple[dt.datetime, str]] = [(self._last_time, self._last_phase)] if history_on else []

    # -------------------------------------------------------------------------
    # State Properties
    # -------------------------------------------------------------------------

    @property
    def last_time(self) -> dt.datetime:
        """
        Timestamp of the most recent update.
        """
        return self._last_time

    @property
    def last_phase(self) -> str:
        """
        Phase value at the most recent update.
        """
        return self._last_phase

    # -------------------------------------------------------------------------
    # Statistical Properties
    # -------------------------------------------------------------------------

    @property
    def total_hours(self) -> float:
        """
        Cumulative elapsed hours since initialization.
        """
        return self._total_hours

    # -------------------------------------------------------------------------
    # History Properties
    # -------------------------------------------------------------------------

    @property
    def history_on(self) -> bool:
        """
        Whether complete history is being recorded.
        """
        return self._history_on

    # -------------------------------------------------------------------------
    # State Update Methods
    # -------------------------------------------------------------------------

    def warmup(self, clock_time: dt.datetime | None = None) -> None:
        """
        Reset statistics while preserving the current phase.

        Clears all accumulated statistics and history, effectively restarting
        the tracking from the specified time while maintaining the current phase.

        Parameters
        ----------
        clock_time : dt.datetime | None, optional
            Reset timestamp. Defaults to the sandbox clock time.
        """
        clock_time = clock_time or self._sandbox.clock_time
        self._initial_time = clock_time
        self._last_time = clock_time
        self._total_hours = 0.0
        self._phase2hours.clear()
        if self._history_on:
            self._history = [(self._last_time, self._last_phase)]

    def update_phase(self, phase: str, clock_time: dt.datetime | None = None) -> None:
        """
        Record a phase transition at the specified time.

        Updates statistics to account for time spent in the previous phase,
        then transitions to the new phase.

        Parameters
        ----------
        phase : str
            New phase value.
        clock_time : dt.datetime | None, optional
            Transition timestamp. Defaults to the sandbox clock time.

        Raises
        ------
        ValueError
            If clock_time is earlier than the last update time, or
            if clock_time is inconsistent with the sandbox clock.
        """
        # Validate clock time consistency
        self._check_clock_time(clock_time)
        clock_time = self._sandbox.clock_time

        # Ensure monotonic time progression
        if clock_time < self._last_time:
            raise ValueError(f"Update time {clock_time} cannot be earlier than last update {self._last_time}")

        # Update statistics for previous phase
        hours = FormatUtils.td2hrs(clock_time - self._last_time)
        self._total_hours += hours
        self._phase2hours[self._last_phase] = \
            self._phase2hours.get(self._last_phase, 0.0) + hours

        # Transition to new phase
        self._last_time = clock_time
        self._last_phase = phase

        # Record history if enabled
        if self._history_on:
            self._history.append((clock_time, phase))

    def update_to_clock_time(self) -> None:
        """
        Synchronize internal time with the sandbox's clock.

        Updates statistics to account for time elapsed since the last update,
        without changing the current phase.
        """
        if self._last_time != self._sandbox.clock_time:
            self.update_phase(self._last_phase)

    def _check_clock_time(self, clock_time: dt.datetime | None = None) -> None:
        """
        Validate clock time consistency with sandbox clock time.

        Parameters
        ----------
        clock_time : dt.datetime | None, optional
            Clock time to validate. If None, no validation is performed.

        Raises
        ------
        ValueError
            If clock_time is provided and differs from sandbox clock time.
        """
        if clock_time is not None and clock_time != self._sandbox.clock_time:
            raise ValueError(f"Clock time mismatch: (provided={clock_time}, sandbox={self._sandbox.clock_time})")

    # -------------------------------------------------------------------------
    # Disposal
    # -------------------------------------------------------------------------

    def dispose(self) -> None:
        super().dispose()

    # -------------------------------------------------------------------------
    # Distribution Analysis Methods
    # -------------------------------------------------------------------------

    def get_proportion(self, phase: str) -> float:
        """
        Calculate the time proportion spent in a specific phase.

        Parameters
        ----------
        phase : str
            Phase value to query.
        
        Returns
        -------
        float
            Proportion of total time spent in the specified phase (0.0 to 1.0).
            Returns 0.0 if no time has elapsed or phase has not been observed.
        """
        self.update_to_clock_time()

        hours = self._phase2hours.get(phase, 0.0)
        return hours / self._total_hours if self._total_hours > 0 else 0.0

    def get_statistics(self) -> dict[str, dict[str, float]]:
        """
        Compute duration and percentage statistics for all observed phases.

        Returns
        -------
        dict[str, dict[str, float]]
            Mapping from phase values to their statistics:
            - "Duration (h)": Total hours spent in the phase
            - "Percentage (%)": Percentage of total time (0-100)
        """
        self.update_to_clock_time()

        result = {}
        for phase, hours in self._phase2hours.items():
            ratio = hours / self._total_hours if self._total_hours > 0 else 0.0
            result[phase] = {
                "Duration (h)": hours,
                "Percentage (%)": ratio * 100
            }
        return result

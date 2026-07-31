from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from o2des.common import AutoIndexed, IDisposable
from o2des.core import IHourCounter, IReadOnlyHourCounter
from o2des.statistics import HourCounterLogger
from o2des.utils import FormatUtils

if TYPE_CHECKING:
    from o2des.core import ISandbox


# =============================================================================
# Read-Only Wrapper
# =============================================================================

class ReadOnlyHourCounter(IReadOnlyHourCounter):
    """
    Read-only wrapper for HourCounter that exposes statistical properties.
    
    This class provides immutable access to an HourCounter's state and computed
    statistics without allowing modifications to the underlying counter.
    """

    def __init__(self, hour_counter: IHourCounter) -> None:
        """
        Initialize read-only wrapper for the specified hour counter.
        
        Parameters
        ----------
        hour_counter : IHourCounter
            The hour counter to wrap with read-only access.
        """
        self._hour_counter: IHourCounter = hour_counter

    # -------------------------------------------------------------------------
    # State Properties
    # -------------------------------------------------------------------------

    @property
    def last_time(self) -> dt.datetime:
        return self._hour_counter.last_time

    @property
    def last_count(self) -> float:
        return self._hour_counter.last_count

    @property
    def paused(self) -> bool:
        return self._hour_counter.paused

    # -------------------------------------------------------------------------
    # Statistical Properties
    # -------------------------------------------------------------------------

    @property
    def total_hours(self) -> float:
        return self._hour_counter.total_hours

    @property
    def cum_value(self) -> float:
        return self._hour_counter.cum_value

    @property
    def total_increment(self) -> float:
        return self._hour_counter.total_increment

    @property
    def total_decrement(self) -> float:
        return self._hour_counter.total_decrement

    @property
    def increment_rate(self) -> float:
        return self._hour_counter.increment_rate

    @property
    def decrement_rate(self) -> float:
        return self._hour_counter.decrement_rate

    @property
    def max_count(self) -> float:
        return self._hour_counter.max_count

    @property
    def average_count(self) -> float:
        return self._hour_counter.average_count

    @property
    def average_duration(self) -> float:
        return self._hour_counter.average_duration

    @property
    def working_time_ratio(self) -> float:
        return self._hour_counter.working_time_ratio


# =============================================================================
# Hour Counter
# =============================================================================

class HourCounter(AutoIndexed, IHourCounter, IDisposable):
    """
    Time-series counter for tracking numerical variables with statistical analysis.
    
    This class tracks a numerical variable that changes over simulation time,
    computing time-weighted statistics such as averages, rates, and durations.
    It supports pausing/resuming observations and optional history tracking.
    """

    def __init__(
        self,
        sandbox: ISandbox,
        initial_time: dt.datetime | None = None,
        keep_history: bool = False,
    ) -> None:
        """
        Initialize a hour counter for the specified sandbox.
        
        Parameters
        ----------
        sandbox : ISandbox
            The owning sandbox instance that provides clock time.
        initial_time : dt.datetime | None, optional
            Initial time. Defaults to the sandbox's current clock time if not provided.
        keep_history : bool, optional
            Whether to record a complete history of observations. Defaults to False.
        """
        super().__init__()
        self._sandbox: ISandbox = sandbox

        # Time tracking
        self._initial_time: dt.datetime = initial_time or self._sandbox.clock_time
        self._last_time: dt.datetime = self._initial_time

        # State variables
        self._last_count: float = 0.0
        self._paused: bool = False

        # Statistical accumulators
        self._total_hours: float = 0.0
        self._cum_value: float = 0.0
        self._total_increment: float = 0.0
        self._total_decrement: float = 0.0
        self._hours_for_count: dict[float, float] = {}

        # Observation history
        self._keep_history: bool = keep_history
        self._history: dict[dt.datetime, float] | None = {} if keep_history else None
        self._logger: HourCounterLogger | None = None

        # Read-only wrapper
        self._read_only: ReadOnlyHourCounter | None = None

    # -------------------------------------------------------------------------
    # State Properties
    # -------------------------------------------------------------------------

    @property
    def last_time(self) -> dt.datetime:
        """
        Timestamp of the most recent observation.
        """
        return self._last_time

    @property
    def last_count(self) -> float:
        """
        Count value at the most recent observation.
        """
        return self._last_count

    @property
    def paused(self) -> bool:
        """
        Whether the counter is currently paused (not at active observation period).
        
        When paused, observations are recorded but statistics are not accumulated
        until resume() is called.
        """
        return self._paused

    # -------------------------------------------------------------------------
    # Statistical Properties
    # -------------------------------------------------------------------------

    @property
    def total_hours(self) -> float:
        """
        Cumulative active observation time in hours since initialization.
        
        Excludes time periods when the counter was paused. Always non-negative.
        """
        return self._total_hours

    @property
    def cum_value(self) -> float:
        """
        Time-weighted cumulative value over active observation period (hour-units).
        
        Computed as the time-integral: ∫count(t)dt over the observation period.
        Represents the area under the time-series curve. Always non-negative.
        """
        return self._cum_value

    @property
    def total_increment(self) -> float:
        """
        Sum of all positive changes observed over active observation period.
        
        Always non-negative.
        """
        return self._total_increment

    @property
    def total_decrement(self) -> float:
        """
        Sum of absolute values of all negative changes over active observation period.
        
        Always non-negative.
        """
        return self._total_decrement

    @property
    def increment_rate(self) -> float:
        """
        Average rate of increments per hour over active observation period.
        
        Computed as total_increment / total_hours if total_hours > 0, else 0.
        Represents average arrival or production rate.
        """
        self.update_to_clock_time()
        return self._total_increment / self._total_hours if self._total_hours > 0 else 0.0

    @property
    def decrement_rate(self) -> float:
        """
        Average rate of decrements per hour over active observation period.
        
        Computed as total_decrement / total_hours if total_hours > 0, else 0.
        Represents average departure or consumption rate.
        """
        self.update_to_clock_time()
        return self._total_decrement / self._total_hours if self._total_hours > 0 else 0.0

    @property
    def max_count(self) -> float:
        """
        Maximum count observed over active observation period.
        """
        valid_count_list = [count for count, hours in self._hours_for_count.items() if hours > 0]
        return max(valid_count_list) if valid_count_list else 0.0

    @property
    def average_count(self) -> float:
        """
        Time-weighted average count over active observation period.
        
        Computed as cum_value / total_hours if total_hours > 0, else last_count.
        Represents average inventory, queue length, or resource utilization.
        """
        self.update_to_clock_time()
        if self._total_hours == 0:
            return self._last_count
        return self._cum_value / self._total_hours

    @property
    def average_duration(self) -> float:
        """
        Average residence time in hours based on Little's Law.
        
        Computed as average_count / decrement_rate if decrement_rate > 0, else 0.
        
        Little's Law: L = λW, where:
        - L: average_count (time-weighted average number in system)
        - λ: decrement_rate (average departure rate)
        - W: average_duration (average time in system)
        
        Valid for stationary processes where increment_rate ≈ decrement_rate.
        Returns 0 when no decrements observed, e.g., initialization phase.
        """
        self.update_to_clock_time()
        if self._total_decrement == 0:
            return 0.0
        return self.average_count / self.decrement_rate

    @property
    def working_time_ratio(self) -> float:
        """
        Proportion of elapsed time over active observation period.
        
        Computed as total_hours / (current_time - initial_time).
        Value in [0, 1] representing fraction of time counter was not paused.
        """
        self.update_to_clock_time()
        elapsed_hours = FormatUtils.td2hrs(self._last_time - self._initial_time)
        if elapsed_hours == 0:
            return 0.0
        return self._total_hours / elapsed_hours

    # -------------------------------------------------------------------------
    # History Properties
    # -------------------------------------------------------------------------

    @property
    def keep_history(self) -> bool:
        """
        Whether complete history is being recorded.
        """
        return self._keep_history

    @property
    def history(self) -> list[tuple[float, float]] | None:
        """
        Historical observations as time-series data points.
        
        Returns
        -------
        list[tuple[float, float]] | None
            List of (hours_since_init, count) tuples sorted chronologically,
            or None if keep_history is False.
        """
        result = None
        if self._keep_history:
            sorted_history = dict(sorted(self._history.items()))
            result = [
                (FormatUtils.td2hrs(timestamp - self._initial_time), count)
                for timestamp, count in sorted_history.items()
            ]
        return result

    # -------------------------------------------------------------------------
    # Logging Configuration
    # -------------------------------------------------------------------------

    def set_logger(self, logger: HourCounterLogger) -> None:
        """
        Attach a HourCounterLogger instance for recording observations to file.

        The logger will immediately receive an initial entry with the current
        cumulative hours and count.

        Parameters
        ----------
        logger : HourCounterLogger
            Pre-configured logger to attach.
        """
        self._logger = logger
        self._logger.log(self._total_hours, self._last_count)

    # -------------------------------------------------------------------------
    # State Update Methods
    # -------------------------------------------------------------------------

    def warmup(self) -> None:
        """
        Reset all statistics while preserving the last count value.
        
        Useful for warm-up periods in simulation where initial transient
        statistics should be discarded. This is a state modification operation
        that resets statistical accumulators to zero but keeps the current count.
        """
        clock_time = self._sandbox.clock_time
        self._initial_time = clock_time
        self._last_time = clock_time
        self._total_hours = 0.0
        self._cum_value = 0.0
        self._total_increment = 0.0
        self._total_decrement = 0.0
        self._hours_for_count.clear()
        if self._keep_history:
            self._history.clear()
        if self._logger is not None and self._logger.log_file:
            self._logger.reset()
            self._logger.log(self._total_hours, self._last_count)

    def observe_count(
        self,
        count: float,
        clock_time: dt.datetime | None = None,
    ) -> None:
        """
        Record an absolute count value at a specific time.
        
        Updates time-series statistics based on the duration since the last
        observation. When paused, the observation updates last_count and last_time
        but does not accumulate statistics.
        
        Parameters
        ----------
        count : float
            New count value to record.
        clock_time : dt.datetime | None, optional
            Observation timestamp. Defaults to sandbox clock time.
        
        Raises
        ------
        ValueError
            If clock_time is earlier than the last observation or doesn't match
            the sandbox clock time.
        """
        # Validate clock time consistency
        self._check_clock_time(clock_time)
        clock_time = self._sandbox.clock_time

        # Ensure monotonic time progression
        if clock_time < self._last_time:
            raise ValueError(
                f"Observation time {clock_time} cannot be earlier than "
                f"last observation {self._last_time}"
            )

        # Update statistics during active observation period
        if not self._paused:
            hours = FormatUtils.td2hrs(clock_time - self._last_time)
            self._total_hours += hours
            self._cum_value += hours * self._last_count

            change = count - self._last_count
            if change > 0:
                self._total_increment += change
            elif change < 0:
                self._total_decrement += abs(change)

            self._hours_for_count[self._last_count] = \
                self._hours_for_count.get(self._last_count, 0.0) + hours

        # Log observation
        if self._logger is not None and self._logger.log_file:
            remark = "Paused" if self._paused else ""
            self._logger.log(self._total_hours, self._last_count, remark)
            if count != self._last_count:
                self._logger.log(self._total_hours, count, remark)

        # Update state
        self._last_time = clock_time
        self._last_count = count

        # Record history if enabled
        if self._keep_history:
            self._history[clock_time] = count

    def observe_change(
        self,
        change: float,
        clock_time: dt.datetime | None = None,
    ) -> None:
        """
        Record a relative change to the count at a specific time.
        
        Convenience method for recording incremental changes.
        Equivalent to observe_count(last_count + change, clock_time).
        
        Parameters
        ----------
        change : float
            Delta to add to the last count (positive for increment, negative for decrement).
        clock_time : dt.datetime | None, optional
            Observation timestamp. Defaults to sandbox clock time.
        """
        self.observe_count(self._last_count + change, clock_time)

    def update_to_clock_time(self) -> None:
        """
        Synchronize internal time with sandbox clock time.
        
        If clock has advanced, records an observation with unchanged count.
        """
        if self._last_time != self._sandbox.clock_time:
            self.observe_count(self._last_count)

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
    # Statistics Accumulation Control Methods
    # -------------------------------------------------------------------------

    def pause(self, clock_time: dt.datetime | None = None) -> None:
        """
        Suspend statistics accumulation while allowing observations.
        
        Transitions to paused state where observations can still be recorded,
        but they won't contribute to cumulative statistics until resumed.
        
        Parameters
        ----------
        clock_time : dt.datetime | None, optional
            Timestamp when to pause. Defaults to sandbox clock time.
        """
        if self._paused:
            return

        self._check_clock_time(clock_time)
        self.observe_count(self._last_count, clock_time)
        self._paused = True
        if self._logger is not None and self._logger.log_file:
            self._logger.log(self._total_hours, self._last_count, "Paused")

    def resume(self, clock_time: dt.datetime | None = None) -> None:
        """
        Resume statistics accumulation after being paused.
        
        Transitions from paused to active state. Time-series statistics
        accumulation continues, but the paused duration is excluded.
        
        Parameters
        ----------
        clock_time : dt.datetime | None, optional
            Timestamp when to resume. Defaults to sandbox clock time.
        """
        if not self._paused:
            return

        self._check_clock_time(clock_time)
        self._last_time = self._sandbox.clock_time
        self._paused = False
        if self._logger is not None and self._logger.log_file:
            self._logger.log(self._total_hours, self._last_count, "Paused")
            self._logger.log(self._total_hours, self._last_count, "")

    # -------------------------------------------------------------------------
    # Disposal
    # -------------------------------------------------------------------------

    def dispose(self) -> None:
        super().dispose()

    # -------------------------------------------------------------------------
    # Read-Only Wrapper
    # -------------------------------------------------------------------------

    def as_read_only(self) -> ReadOnlyHourCounter:
        """
        Create or return cached read-only wrapper for this counter.
        
        Returns
        -------
        ReadOnlyHourCounter
            Read-only interface to this counter's state and statistics.
        """
        if self._read_only is None:
            self._read_only = ReadOnlyHourCounter(self)
        return self._read_only

    # -------------------------------------------------------------------------
    # Distribution Analysis Methods
    # -------------------------------------------------------------------------

    def percentile(self, ratio: float) -> float:
        """
        Calculate time-based percentile of count values.
        
        Parameters
        ----------
        ratio : float
            Percentile value between 0 and 100.
        
        Returns
        -------
        float
            Count value below which the specified percentage of time was spent.
            Returns inf if no observations recorded.
        """
        if not self._hours_for_count:
            return float('inf')

        sorted_counts = dict(sorted(self._hours_for_count.items()))
        threshold = sum(sorted_counts.values()) * ratio / 100

        for count, hours in sorted_counts.items():
            threshold -= hours
            if threshold <= 0:
                return count

        return float('inf')

    def histogram(
        self,
        count_interval: float,
    ) -> dict[float, tuple[float, float, float]]:
        """
        Generate histogram of time spent at different count ranges.
        
        Parameters
        ----------
        count_interval : float
            Width of each count value interval (bin size).
        
        Returns
        -------
        dict[float, tuple[float, float, float]]
            Mapping from interval lower bound to (total_hours, probability, cumulative_probability).
            Empty dict if no observations recorded.
        """
        if not self._hours_for_count:
            return {}

        # Bin counts into intervals
        interval_hours: dict[float, float] = {}
        for count, hours in self._hours_for_count.items():
            lower_bound = (count // count_interval) * count_interval
            # Adjust boundary case where count equals lower bound
            if lower_bound > 0 and lower_bound == count:
                lower_bound -= count_interval
            interval_hours[lower_bound] = interval_hours.get(lower_bound, 0.0) + hours

        # Calculate statistics
        total_hours = sum(interval_hours.values())
        if total_hours == 0:
            return {}

        result: dict[float, tuple[float, float, float]] = {}
        cumulative_hours = 0.0

        for lower_bound in sorted(interval_hours.keys()):
            hours = interval_hours[lower_bound]
            cumulative_hours += hours
            probability = hours / total_hours
            cumulative_probability = cumulative_hours / total_hours

            result[lower_bound] = (
                round(hours, 2),
                round(probability, 2),
                round(cumulative_probability, 2)
            )

        return result

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod


# =============================================================================
# Hour Counter Interfaces
# =============================================================================

class IReadOnlyHourCounter(ABC):
    """
    Read-only interface for time-series statistics of a numerical variable.
    
    Provides access to computed time-series statistics of a time-varying numerical
    variable observed during simulation. Statistics are calculated from time-stamped
    observations and account for the duration between observations.
    
    All properties are read-only and derived from the historical time-series data.
    """

    # -------------------------------------------------------------------------
    # State Properties
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def last_time(self) -> dt.datetime:
        """
        Timestamp of the most recent observation.
        """
        ...

    @property
    @abstractmethod
    def last_count(self) -> float:
        """
        Count value at the most recent observation.
        """
        ...

    @property
    @abstractmethod
    def paused(self) -> bool:
        """
        Whether the counter is currently paused (not at active observation period).
        
        When paused, observations are recorded but statistics are not accumulated
        until resume() is called.
        """
        ...

    # -------------------------------------------------------------------------
    # Statistical Properties
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def total_hours(self) -> float:
        """
        Cumulative active observation time in hours since initialization.
        
        Excludes time periods when the counter was paused. Always non-negative.
        """
        ...

    @property
    @abstractmethod
    def cum_value(self) -> float:
        """
        Time-weighted cumulative value over active observation period (hour-units).
        
        Computed as the time-integral: ∫count(t)dt over the observation period.
        Represents the area under the time-series curve. Always non-negative.
        """
        ...

    @property
    @abstractmethod
    def total_increment(self) -> float:
        """
        Sum of all positive changes over active observation period.
        
        Always non-negative.
        """
        ...

    @property
    @abstractmethod
    def total_decrement(self) -> float:
        """
        Sum of absolute values of all negative changes over active observation period.
        
        Always non-negative.
        """
        ...

    @property
    @abstractmethod
    def increment_rate(self) -> float:
        """
        Average rate of increments per hour over active observation period.
        
        Computed as total_increment / total_hours if total_hours > 0, else 0.
        Represents average arrival or production rate.
        """
        ...

    @property
    @abstractmethod
    def decrement_rate(self) -> float:
        """
        Average rate of decrements per hour over active observation period.
        
        Computed as total_decrement / total_hours if total_hours > 0, else 0.
        Represents average departure or consumption rate.
        """
        ...

    @property
    @abstractmethod
    def max_count(self) -> float:
        """
        Maximum count observed over active observation period.
        """
        ...

    @property
    @abstractmethod
    def average_count(self) -> float:
        """
        Time-weighted average count over active observation period.
        
        Computed as cum_value / total_hours if total_hours > 0, else 0.
        Represents average inventory, queue length, or resource utilization.
        """
        ...

    @property
    @abstractmethod
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
        ...

    @property
    @abstractmethod
    def working_time_ratio(self) -> float:
        """
        Proportion of elapsed time over active observation period.
        
        Computed as total_hours / (current_time - initial_time).
        Value in [0, 1] representing fraction of time counter was not paused.
        """
        ...


class IHourCounter(IReadOnlyHourCounter):
    """
    Mutable interface for recording time-stamped observations of a time-varying
    numerical variable.
    
    Extends IReadOnlyHourCounter with methods to record time-stamped observations,
    control pause/resume of time-series tracking, and manage lifecycle.
    
    Supports both absolute count observations and relative change observations,
    allowing flexible integration with various time-series simulation scenarios.
    """

    # -------------------------------------------------------------------------
    # State Update Methods
    # -------------------------------------------------------------------------

    @abstractmethod
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
        ...

    @abstractmethod
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
        ...

    # -------------------------------------------------------------------------
    # Statistics Accumulation Control Methods
    # -------------------------------------------------------------------------

    @abstractmethod
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
        ...

    @abstractmethod
    def resume(self, clock_time: dt.datetime | None = None) -> None:
        """
        Resume statistics accumulation after being paused.
        
        Transitions from paused to active state. Time-series statistics
        accumulation continues, but the paused duration is excluded.
        
        Parameters
        ----------
        clock_time : datetime, optional
            Timestamp when to resume. Defaults to sandbox clock time.
        """
        ...

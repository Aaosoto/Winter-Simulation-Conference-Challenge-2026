"""
O2DES Activity Handler - reference activity state machine behavior.

4-state state machine (matching the reference behavior):
  r_loads_requested_start  → entities waiting to START this activity
  s_loads_started         → entities currently ACTIVE (duration running)
  d_loads_ready_finish     → entities finished active, waiting to FINISH
  f_loads_finished        → entities finished, waiting to DEPART

Transitions:
  R → S: start(entity)            [attempt_start loop calls start for each R entity]
  S → D: ready_finish(entity)     [scheduled after T_Duration]
  D → F: finish(entity)          [attempt_finish loop calls finish for each D entity]
  F → exit: depart(entity)       [next activity calls depart, or terminal]

signal_start(entity): adds entity to R, schedules attempt_start
signal_finish(entity): adds entity to D (d_hour_counter +1), schedules attempt_finish

State storage uses self.__dict__ keys so that subclasses can freely define
their own _xxx instance attributes without shadowing the state sets.
"""

import datetime as dt
import logging
from typing import Any, Callable, Generic, Optional, TypeVar

from o2des.common import ActionSet
from o2des.core import HourCounter, Sandbox
from .ordered_set import OrderedSet

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Keys for state storage in self.__dict__
_R_KEY = '_r_lrs'
_S_KEY = '_s_ls'
_D_KEY = '_d_lrf'
_F_KEY = '_f_lf'


class ActivityHandler(Sandbox, Generic[T]):
    """
    State machine handler for a single activity.

    Subclasses implement:
      - start(entity)     [S-side: duration, statistics, on_start actions]
      - finish(entity)    [D-side: downstream signal, statistics, on_finish actions]

    State stored directly in self.__dict__ with keys (_r_lrs, _s_ls, _d_lrf, _f_lf)
    so that subclass instance attribute declarations do NOT shadow it.
    """

    EnableLog: bool = False

    def __init__(self, seed: int = 0, id: str = ""):
        super().__init__(seed=seed, uid=id)

        # State: stored directly in __dict__ to avoid subclass shadowing
        self.__dict__[_R_KEY] = OrderedSet()
        self.__dict__[_S_KEY] = OrderedSet()
        self.__dict__[_D_KEY] = OrderedSet()
        self.__dict__[_F_KEY] = OrderedSet()

        # Hour counters: created eagerly at construction, matching the
        # reference activity handler's construction-time counter setup.
        # This ensures _creation_time = clock_time = 0 (simulation start),
        # not the time of first observe_change (which would shrink the
        # denominator and inflate time-weighted averages).
        self.__dict__['_r_hc'] = self.add_hour_counter()
        self.__dict__['_s_hc'] = self.add_hour_counter()
        self.__dict__['_d_hc'] = self.add_hour_counter()
        self.__dict__['_f_hc'] = self.add_hour_counter()

        # Duration function: entity -> timedelta or float (hours)
        self._t_duration: Optional[Callable[[T, Any], Optional[dt.timedelta]]] = None

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)
        self.enable_log = False

        # Compatibility alias for old code that uses _active_loads
        # (Reference ActivityHandler stores active loads in s_loads_started)
        self._active_loads = self.__dict__[_S_KEY]

    # -------------------------------------------------------------------------
    # State accessors — use __dict__ keys so subclass attributes can't shadow them
    # -------------------------------------------------------------------------

    @property
    def r_loads_requested_start(self) -> 'OrderedSet[T]':
        return self.__dict__[_R_KEY]

    @property
    def s_loads_started(self) -> 'OrderedSet[T]':
        return self.__dict__[_S_KEY]

    @property
    def d_loads_ready_finish(self) -> 'OrderedSet[T]':
        return self.__dict__[_D_KEY]

    @property
    def f_loads_finished(self) -> 'OrderedSet[T]':
        return self.__dict__[_F_KEY]

    @property
    def r_hour_counter(self) -> HourCounter:
        hc = self.__dict__['_r_hc']
        if hc is None:
            hc = self.add_hour_counter()
            self.__dict__['_r_hc'] = hc
        return hc

    @property
    def s_hour_counter(self) -> HourCounter:
        hc = self.__dict__['_s_hc']
        if hc is None:
            hc = self.add_hour_counter()
            self.__dict__['_s_hc'] = hc
        return hc

    @property
    def d_hour_counter(self) -> HourCounter:
        hc = self.__dict__['_d_hc']
        if hc is None:
            hc = self.add_hour_counter()
            self.__dict__['_d_hc'] = hc
        return hc

    @property
    def f_hour_counter(self) -> HourCounter:
        hc = self.__dict__['_f_hc']
        if hc is None:
            hc = self.add_hour_counter()
            self.__dict__['_f_hc'] = hc
        return hc

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    # -------------------------------------------------------------------------
    # Public Signal API
    # -------------------------------------------------------------------------

    def signal_start(self, entity: T) -> None:
        """External: entity requests to start this activity (R → ?)."""
        if entity is None:
            return
        if entity not in self.__dict__[_R_KEY]:
            self.__dict__[_R_KEY].add(entity)
            self.r_hour_counter.observe_change(1)
        self.schedule(self.attempt_start)

    def signal_finish(self, entity: T) -> None:
        """External: entity is ready to finish (D → ?, schedules attempt_finish)."""
        if entity is None:
            return
        d = self.__dict__[_D_KEY]
        if entity not in d:
            d.add(entity)
            self.d_hour_counter.observe_change(1)
        self.schedule(self.attempt_finish)

    def depart(self, entity: T) -> None:
        """External: remove entity from F (F → exit)."""
        f = self.__dict__[_F_KEY]
        if entity not in f:
            return
        f.discard(entity)
        self.f_hour_counter.observe_change(-1)
        self.schedule(self.attempt_start)

    # -------------------------------------------------------------------------
    # Internal state machine
    # -------------------------------------------------------------------------

    def attempt_start(self) -> None:
        """Try to start all entities in R."""
        if self.enable_log:
            logger.debug("[%s] attempt_start R=%d", self.uid, len(self.__dict__[_R_KEY]))
        for entity in list(self.__dict__[_R_KEY]):
            self.start(entity)

    def start(self, entity: T) -> None:
        """
        start an entity: R → S.

        - Removes from R, adds to S (+s_hour_counter)
        - Schedules ready_finish(entity) after T_Duration
        - Invokes on_start actions

        Subclass overrides do activity-specific logic (stats, etc.)
        BEFORE calling super().start(entity).
        """
        # R → S transition
        r = self.__dict__[_R_KEY]
        s = self.__dict__[_S_KEY]
        if entity not in r:
            return
        r.discard(entity)
        self.r_hour_counter.observe_change(-1)
        if entity not in s:
            s.add(entity)
            self.s_hour_counter.observe_change(1)

        # Duration and ready_finish scheduling
        duration = dt.timedelta(0)
        if self._t_duration is not None:
            rs = self._default_rs
            dur = self._t_duration(entity, rs)
            if isinstance(dur, dt.timedelta):
                duration = dur
            elif isinstance(dur, (int, float)):
                duration = dt.timedelta(hours=dur)
            elif hasattr(dur, 'TotalHours'):
                duration = dt.timedelta(hours=dur.total_hours)

        self.schedule(lambda e=entity: self.ready_finish(e), delay=duration)
        self._on_start.invoke(entity)

    def ready_finish(self, entity: T) -> None:
        """Marks entity as ready to finish: S → D."""
        s = self.__dict__[_S_KEY]
        d = self.__dict__[_D_KEY]
        if entity not in s:
            return
        s.discard(entity)
        self.s_hour_counter.observe_change(-1)
        if entity not in d:
            d.add(entity)
            self.d_hour_counter.observe_change(1)
        self.schedule(self.attempt_finish)

    def attempt_finish(self) -> None:
        """Try to finish all entities in D."""
        if self.enable_log:
            logger.debug("[%s] attempt_finish D=%d", self.uid, len(self.__dict__[_D_KEY]))
        for entity in list(self.__dict__[_D_KEY]):
            self.finish(entity)

    def finish(self, entity: T) -> None:
        """
        finish an entity: D → F.

        - Removes from D, adds to F (+f_hour_counter)
        - Invokes on_finish actions
        """
        d = self.__dict__[_D_KEY]
        f = self.__dict__[_F_KEY]
        if entity not in d:
            return
        d.discard(entity)
        self.d_hour_counter.observe_change(-1)
        if entity not in f:
            f.add(entity)
            self.f_hour_counter.observe_change(1)
        self._on_finish.invoke(entity)

    def reset_statistics(self) -> None:
        """Reset this activity's counters at the measurement-period boundary.

        Counter values are preserved so entities already waiting, sailing, or
        being served at the end of warm-up remain represented from time zero of
        the formal measurement period.
        """
        for counter in self.hour_counters:
            counter.warmup()

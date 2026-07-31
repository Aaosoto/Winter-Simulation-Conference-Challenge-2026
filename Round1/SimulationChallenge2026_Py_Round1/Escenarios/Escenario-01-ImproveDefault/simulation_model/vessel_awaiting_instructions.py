"""
Vessel Awaiting Instructions Activity.

Reference behavior: ActivityHandler<Vessel> with:
  - _initializedRoutes: tracks which routes have had first vessel departure scheduled
  - q_finish_signals: route finish-signal tokens (one per vessel release)
  - _headway = TimeSpan.FromDays(7) (fixed field, not property)
  - attempt_finish: handles BOTH first-vessel init AND subsequent-vessel release
    (Python start override is REMOVED — initialization only in attempt_finish)
  - First vessel: route not in _initializedRoutes → schedule initial delay,
    add to _initializedRoutes, continue (do NOT finish)
  - Subsequent vessels: route in q_finish_signals → consume token,
    finish(vessel), schedule next _signal_finish with _headway

on_finish(Vessel) → VesselSailing.signal_start(vessel)
"""

import datetime as dt
from typing import TYPE_CHECKING

from o2des.common import ActionSet
from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet

if TYPE_CHECKING:
    from maritime_data_context import (
        ServiceRoute
    )


class VesselAwaitingInstructions(ActivityHandler):
    """
    Holds vessels that are ready to depart on their assigned service routes.

    start: vessel enters R (waiting pool)
    finish: controlled by route-specific headway schedule
      - First vessel of route: computes initial delay from StartDayOfWeek,
        schedules _signal_finish(route) to fire when vessel should depart
      - Subsequent vessels: wait in D until _signal_finish fires
      - When headway fires: first waiting vessel moves D→F, next headway scheduled

    on_finish (vessel) → VesselSailing.signal_start(vessel) [via _connect_event_flow wiring]
    """

    def __init__(self, seed: int = 0):
        super().__init__(seed=seed, id="VesselAwaitingInstructions")

        # Routes that have been initialized (first vessel departure scheduled)
        self._initialized_routes: OrderedSet['ServiceRoute'] = OrderedSet()
        # Routes that have a pending finish-signal token
        self._q_finish_signals: OrderedSet['ServiceRoute'] = OrderedSet()

        # Fixed 7-day headway between consecutive vessel releases on the same route
        # Reference: private readonly TimeSpan _headway = TimeSpan.FromDays(7);
        self._headway = dt.timedelta(days=7)

        self._on_finish = ActionSet(object)

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    # -------------------------------------------------------------------------
    # attempt_finish — Reference logic (no start override)
    # -------------------------------------------------------------------------

    def attempt_finish(self) -> None:
        """
        Reference attempt_finish logic exactly matched:
          for vessel in d_loads_ready_finish:
            route = vessel.assigned_service_route
            if route not initialized:
                _initializedRoutes.Add(route)
                delay = ComputeInitialDelay(route)
                Schedule(() => signal_finish(route), delay)
                continue        ← first vessel: just schedule, don't finish
            if route in q_finish_signals:
                q_finish_signals.Remove(route)
                finish(vessel)  ← subsequent: finish + schedule next headway
                Schedule(() => signal_finish(route), _headway)
        """
        for vessel in list(self.d_loads_ready_finish):
            route = vessel.assigned_service_route

            # First vessel of this route: schedule initial release (don't finish yet)
            if route not in self._initialized_routes:
                self._initialized_routes.add(route)
                delay = self._compute_initial_delay(route)
                self.schedule(lambda r=route: self._signal_finish(r), delay=delay)
                continue

            # Subsequent vessels: require a finish-signal token
            if route in self._q_finish_signals:
                self._q_finish_signals.discard(route)

                # IMPORTANT: Do NOT modify vessel route or location state here.
                # Vessel is assumed to already be positioned correctly
                # (e.g., at the first port during initialization).

                # D → F transition (base class finish handles this + on_finish)
                self.finish(vessel)

                # Schedule next headway release for this route
                self.schedule(lambda r=route: self._signal_finish(r), delay=self._headway)

    # -------------------------------------------------------------------------
    # Headway signal and helpers
    # -------------------------------------------------------------------------

    def _signal_finish(self, route: 'ServiceRoute') -> None:
        """Issue a finish-signal token for a route (fires next attempt_finish)."""
        if route not in self._q_finish_signals:
            self._q_finish_signals.add(route)
        self.schedule(self.attempt_finish)

    def _compute_initial_delay(self, route: 'ServiceRoute') -> dt.timedelta:
        """
        Compute delay until the next occurrence of StartDayOfWeek.

        StartDayOfWeek is in [0, 7), where 0 = Monday 00:00.
        
        Reference behavior:
          double startDay = route.start_day_of_week;
          double nowDay = ((int)ClockTime.DayOfWeek + 6) % 7 + ClockTime.TimeOfDay.TotalDays;
        
        Reference weekday convention: Sunday=0, Monday=1, ..., Saturday=6
        ((int)DayOfWeek + 6) % 7 maps: Sunday→6, Monday→0, ..., Saturday→5
        
        Python weekday(): Monday=0, Tuesday=1, ..., Sunday=6
        (already in Monday=0 convention — NO +6 transformation needed!)
        """
        start_day = route.start_day_of_week
        # Current simulation time as fractional days [0, 7), Monday=0
        current_time = self.clock_time
        total_seconds = (current_time.hour * 3600 + current_time.minute * 60
                         + current_time.second + current_time.microsecond / 1e6)
        current_day_fraction = total_seconds / 86400.0
        current_dow = current_time.weekday()  # Monday=0, ... Sunday=6
        current_day = current_dow + current_day_fraction

        delay_days = start_day - current_day
        if delay_days < 0:
            delay_days += 7.0

        return dt.timedelta(days=max(0, delay_days))
"""
Vessel Sailing Activity.

Duration-driven activity where vessels sail along their current segment.
Duration = sailing_distance / sailing_speed with ±5% random variation.
Tracks TEU capacity and carried TEU statistics by service route.
"""

import datetime as dt
from typing import TYPE_CHECKING, Dict

from o2des.common import ActionSet
from o2des.core import HourCounter
from .activity_handler import ActivityHandler

if TYPE_CHECKING:
    from maritime_data_context import (
        MaritimeDataContext, Vessel, ServiceRoute
    )


class VesselSailing(ActivityHandler):
    """
    Represents the sailing activity of a vessel along its current segment.

    Duration = leg.sailing_distance / vesselClass.sailing_speed
    with a ±5% random variation factor (0.95 to 1.05).

    Tracks TEU capacity and carried TEU by service route.

    State machine matching the reference O2DES activity handler:
      r_loads_requested_start → s_loads_started → d_loads_ready_finish → f_loads_finished
      VesselGenerator calls signal_start(vessel) → vessel enters R
      attempt_start → start(vessel) → vessel enters S (duration scheduled)
      Duration expires → ready_finish(vessel) → vessel enters D
      attempt_finish → finish(vessel) → vessel enters F
      _connect_event_flow wires on_finish → next_activity.signal_start
    """

    def __init__(self, data_context: 'MaritimeDataContext' = None, seed: int = 0):
        super().__init__(seed=seed, id="VesselSailing")

        # Duration is vessel-specific, matching the reference behavior:
        #   T_Duration = (vessel, rs) => GetDuration(vessel, rs);
        # The Reference ActivityHandler passes DefaultRS as `rs`; this lambda
        # uses the activity's own _default_rs which is the same instance.
        self._t_duration = lambda vessel, rs: self._get_duration(vessel)

        # Statistics — eagerly create one HourCounter per service route so
        # that _creation_time = sandbox.clock_time = 0 (sim start), matching
        # the reference implementation's AddHourCounter() which uses _initialTime = DateTime.MinValue
        # and effectively divides by (now - DateTime.MinValue) ≈ now.
        # Without eager creation, the lazy per-route counter would use
        # _creation_time = first-observation-time, inflating the integral's
        # denominator mismatch and biasing the time-weighted average.
        self._hc_teu_capacity_by_service_route: Dict['ServiceRoute', HourCounter] = {}
        self._hc_carried_teus_by_service_route: Dict['ServiceRoute', HourCounter] = {}
        if data_context is not None:
            for route in data_context.service_routes:
                self._hc_teu_capacity_by_service_route[route] = self.add_hour_counter()
                self._hc_carried_teus_by_service_route[route] = self.add_hour_counter()

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

    @property
    def hc_teu_capacity_by_service_route(self) -> Dict['ServiceRoute', HourCounter]:
        return self._hc_teu_capacity_by_service_route

    @property
    def hc_carried_teus_by_service_route(self) -> Dict['ServiceRoute', HourCounter]:
        return self._hc_carried_teus_by_service_route

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    def _get_duration(self, vessel: 'Vessel') -> dt.timedelta:
        """Compute sailing duration for the given vessel."""
        current_segment = vessel.current_segment

        if current_segment is None:
            return dt.timedelta(0)

        leg = current_segment.associated_leg
        vessel_class = vessel.vessel_class

        speed = vessel_class.sailing_speed
        if speed <= 0:
            return dt.timedelta(0)

        hours = leg.sailing_distance / speed
        hours *= leg.sailing_time_multiplier

        # Apply ±5% random variation
        variation_factor = 0.95 + 0.10 * self._default_rs.next_double()
        hours *= variation_factor

        return dt.timedelta(hours=hours)

    def start(self, vessel: 'Vessel') -> None:
        """
        start a vessel on its sailing segment.

        Reference behavior:
          base.start(vessel)  # R→S, schedule ready_finish, fire on_start
          # Then record stats
        """
        # Call base class start first (R→S, schedule ready_finish with duration)
        # Base class start already calls self._on_start.invoke(entity)
        super().start(vessel)

        # Stats: record capacity and cargo when vessel starts sailing (reference order: after base.start)
        service_route = vessel.assigned_service_route
        vessel_class = vessel.vessel_class
        teu_capacity = vessel_class.teu_capacity
        carried_teus = sum(s.teu_size for s in vessel.carried_shipments)

        # Counter is pre-created at Activity ctor (matching the reference behavior AddHourCounter).
        # If the route was unknown at ctor (e.g. no data_context), fall back
        # to lazy creation — but this is no longer the default path.
        if service_route not in self._hc_teu_capacity_by_service_route:
            self._hc_teu_capacity_by_service_route[service_route] = self.add_hour_counter()
        self._hc_teu_capacity_by_service_route[service_route].observe_change(teu_capacity)

        if service_route not in self._hc_carried_teus_by_service_route:
            self._hc_carried_teus_by_service_route[service_route] = self.add_hour_counter()
        self._hc_carried_teus_by_service_route[service_route].observe_change(carried_teus)

    def finish(self, vessel: 'Vessel') -> None:
        """
        finish a vessel's sailing segment.

        Reference behavior (ActivityHandler.finish):
          - Remove from D, add to F (+f_hour_counter)
          - Call on_finish actions

        Stats removal happens in depart(), matching the reference behavior VesselSailing.depart().
        """
        super().finish(vessel)

    def depart(self, vessel: 'Vessel') -> None:
        """
        Remove vessel from sailing activity (F → exit).

        Reference VesselSailing.depart(): checks f_loads_finished, calls base.depart(),
        then removes TEU capacity and carried TEU statistics.
        """
        if vessel not in self.f_loads_finished:
            return

        # Stats: remove capacity and cargo when vessel departs sailing
        service_route = vessel.assigned_service_route
        vessel_class = vessel.vessel_class
        teu_capacity = vessel_class.teu_capacity
        carried_teus = sum(s.teu_size for s in vessel.carried_shipments)

        super().depart(vessel)

        if service_route in self._hc_teu_capacity_by_service_route:
            self._hc_teu_capacity_by_service_route[service_route].observe_change(-teu_capacity)
        if service_route in self._hc_carried_teus_by_service_route:
            self._hc_carried_teus_by_service_route[service_route].observe_change(-carried_teus)

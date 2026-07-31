"""
Vessel Queuing For Berth Activity.

start side:
  - Vessel arrives at a port (signals via signal_start(vessel)).
  - Records vessel queue statistics by port.

finish side:
  - Berth signals completion of cargo handling (signal_finish(berth)).
  - Matches idle berth to a waiting vessel by port.
  - If no vessel is waiting at that port, berth goes back to idle.

Reference behavior:
  - Uses base class R/S/D/F state (no shadow sets)
  - signal_finish(berth) adds berth to q_finish_signals, schedules attempt_finish
  - attempt_finish iterates Q, finds vessel from berth.occupying_vessel,
    checks d_loads_ready_finish, sets vessel.current_berth = berth, calls finish(vessel)
  - on_finish → VBS.signal_start(vessel) [via ConnectTo wiring in model.py]
"""

from typing import TYPE_CHECKING, Dict, Set

from o2des.common import ActionSet
from o2des.core import HourCounter
from config.simulation_config import ENABLE_STRATEGY

from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet
from response_strategies.default_strategy import DefaultStrategy
from response_strategies.strategy_validation import (
    capture_alternative_route_strategy_state,
    validate_alternative_route_strategy_result,
)
from response_strategies.user_strategy import UserStrategy

if TYPE_CHECKING:
    from maritime_data_context import (
        MaritimeDataContext, Port, Vessel, Berth
    )


class VesselQueuingForBerth(ActivityHandler):
    """
    Represents vessels waiting in queue for berth assignment.

    start side:
      - No gating. Vessels enter the queue immediately.
      - on_start → record hc_number_of_vessels_by_port statistics.

    finish side:
      - Controlled by berth signals.
      - Each berth signal releases exactly one vessel, identified by berth.occupying_vessel.
      - on_finish → VesselBeingServed.signal_start(vessel) [via ConnectTo wiring]
    """

    def __init__(self, data_context: 'MaritimeDataContext' = None, seed: int = 0):
        super().__init__(seed=seed, id="VesselQueuingForBerth")
        self._data_context = data_context

        # finish side: pending berth finish signals (berths ready to release vessel)
        self._q_finish_signals: OrderedSet['Berth'] = OrderedSet()

        # Statistics - Time-weighted vessel counters grouped by port.
        # Eagerly create one HourCounter per port so _creation_time = sim
        # start (= 0), matching the reference behavior's AddHourCounter() semantics. Without
        # this, the first vessel to visit a port would create its counter
        # late, biasing the per-port time-weighted vessel average upward.
        self._hc_number_of_vessels_by_port: Dict['Port', HourCounter] = {}
        if data_context is not None:
            for port in data_context.ports:
                self._hc_number_of_vessels_by_port[port] = self.add_hour_counter()

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

    @property
    def hc_number_of_vessels_by_port(self) -> Dict['Port', HourCounter]:
        return self._hc_number_of_vessels_by_port

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    @property
    def q_finish_signals(self) -> Set['Berth']:
        """Berth signals waiting to release vessels."""
        return self._q_finish_signals

    def signal_finish(self, berth: 'Berth') -> None:
        """
        External signal indicating that a berth is ready to admit its occupying vessel.
        """
        if berth is None:
            return
        if berth not in self._q_finish_signals:
            self._q_finish_signals.add(berth)
            self.schedule(self.attempt_finish)

    def attempt_finish(self) -> None:
        """
        Reference VesselQueuingForBerth.attempt_finish:
          for each berth in q_finish_signals:
            vessel = berth.occupying_vessel
            if vessel not in d_loads_ready_finish: continue
            q_finish_signals.Remove(berth)
            vessel.current_berth = berth
            finish(vessel)
        """
        for berth in list(self._q_finish_signals):
            vessel = berth.occupying_vessel
            if vessel is None:
                continue
            if vessel not in self.d_loads_ready_finish:
                continue
            self._q_finish_signals.discard(berth)
            vessel.current_berth = berth
            self._adjust_carried_shipments_before_cargo_handling(vessel)
            self.finish(vessel)

    # -------------------------------------------------------------------------
    # Statistics - Number of Vessels by Port
    # -------------------------------------------------------------------------

    def start(self, vessel: 'Vessel') -> None:
        """
        Override to record port-specific vessel queue statistics.

        Reference behavior order: base.start first (R→S, schedule, on_start),
        then stats observe_change(+1).
        """
        super().start(vessel)

        port = self._get_arrival_port_for_statistics(vessel)
        if port is not None:
            # Counter is pre-created at ctor; this fallback handles the
            # case where data_context was not supplied.
            if port not in self._hc_number_of_vessels_by_port:
                self._hc_number_of_vessels_by_port[port] = self.add_hour_counter()
            self._hc_number_of_vessels_by_port[port].observe_change(1)

    def depart(self, vessel: 'Vessel') -> None:
        """
        Override to update port-specific vessel queue statistics on departure.

        Reference depart() (VesselQueuingForBerth.cs lines 112-130):
          if (f_loads_finished.Contains(vessel)) {
              base.depart(vessel);                          // FIRST
              portCounter.ObserveChange(-1);                // THEN stats
          }
        Order matters: base.depart() advances F-HourCounter and may free
        capacity. The reference implementation raises if no portCounter exists; Python previously
        silently no-op'd. We now raise ValueError to match reference behaviour.
        """
        if vessel in self.f_loads_finished:
            port = self._get_arrival_port_for_statistics(vessel)
            super().depart(vessel)
            if port is None:
                return
            if port not in self._hc_number_of_vessels_by_port:
                raise ValueError(
                    f"Cannot update vessel queue statistics for Vessel {vessel.index}: "
                    f"no HourCounter exists for port "
                    f"{getattr(port, 'Name', port)}. Vessel may not have "
                    f"started this activity before departure."
                )
            self._hc_number_of_vessels_by_port[port].observe_change(-1)

    def _get_arrival_port_for_statistics(self, vessel: 'Vessel') -> 'Port':
        """
        Reference GetArrivalPortForStatistics:
          - If CurrentSegment is null: use first segment's DeparturePort
          - Else: use CurrentSegment.associated_leg.arrival_port
        """
        if vessel.current_segment is not None:
            leg = vessel.current_segment.associated_leg
            if leg is not None:
                return leg.arrival_port

        # CurrentSegment is null — use first segment's departure port
        route = vessel.assigned_service_route
        if route is not None and route.segments:
            first_segment = sorted(route.segments, key=lambda s: s.sequence_index)[0]
            if first_segment.associated_leg is not None:
                return first_segment.associated_leg.departure_port

        return None

    def _adjust_carried_shipments_before_cargo_handling(self, vessel: 'Vessel') -> None:
        if (
            self._data_context is None
            or not ENABLE_STRATEGY
        ):
            return

        route_snapshot = capture_alternative_route_strategy_state(
            self._data_context
        )
        route_decision = UserStrategy.create_alternative_service_routes(
            self._data_context, self.clock_time, vessel
        )
        validate_alternative_route_strategy_result(
            self._data_context, route_snapshot
        )
        if route_decision is None:
            DefaultStrategy.create_alternative_service_routes(
                self._data_context, self.clock_time, vessel
            )

        user_decision = UserStrategy.adjust_bookings_before_cargo_handling(
            self._data_context, self.clock_time, vessel
        )
        if user_decision is None:
            DefaultStrategy.adjust_bookings_before_cargo_handling(
                self._data_context, self.clock_time, vessel
            )

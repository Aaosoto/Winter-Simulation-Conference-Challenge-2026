"""
Berth Idle Activity.

State machine (ActivityHandler<Berth>):
  R → S → D → F → exit (via ConnectTo wiring)
  [Berth flow: BerthIdle → BerthBerthing → BerthHandlingCargo → BerthIdle]

on_finish (Berth) → BerthBerthing.RequestStart(berth)
  [via _connect_event_flow: BerthIdle.on_finish → BerthBerthing.RequestStart]

Vessel queueing for berth (cross-flow signal):
  VesselQueuingForBerth.on_start fires BerthIdle.signal_finish(vessel)
  to queue a vessel that wants to occupy a berth.
  BerthIdle.signal_finish(vessel) adds vessel to q_finish_signals, schedules attempt_finish.
  attempt_finish matches vessels from Q to idle berths (in D) by port,
  then calls finish(berth) to transition the matched berth to F.
"""

from typing import TYPE_CHECKING, Dict

from o2des.common import ActionSet
from o2des.core import HourCounter
from config.simulation_config import ENABLE_STRATEGY, PORT_CONGESTION_MULTIPLIER
from response_strategies.default_strategy import DefaultStrategy
from response_strategies.user_strategy import UserStrategy
from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet

if TYPE_CHECKING:
    from maritime_data_context import (
        MaritimeDataContext, Port, Vessel, Berth
    )


class BerthIdle(ActivityHandler):
    """
    Represents a berth in the idle state, available for vessel occupation.

    State transitions (ActivityHandler<Berth>):
      R → S: start(berth)          [berth becomes active, capacity stats]
      S → D: ready_finish(berth)    [scheduled after 0 duration, berth is "ready"]
      D → F: finish(berth)         [attempt_finish calls finish, triggers next activity]

    on_finish (Berth) → BerthBerthing.RequestStart(berth)

    Vessel queueing:
      - VesselQueuingForBerth.on_start fires BerthIdle.signal_finish(vessel)
      - Vessel waits in q_finish_signals
      - attempt_finish matches vessels in Q to idle berths in D by port
      - Matched berth: finish(berth) called, vessel.current_berth = berth
    """

    def __init__(self, data_context: 'MaritimeDataContext' = None, seed: int = 0):
        super().__init__(seed=seed, id="BerthIdle")
        self._data_context = data_context

        # Statistics
        self._hc_teu_capacity_by_port: Dict['Port', HourCounter] = {}

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

        # Vessel waiting list: vessels queued by VesselQueuingForBerth.on_start
        self._q_finish_signals: OrderedSet['Vessel'] = OrderedSet()
        self._waiting_since_by_vessel = {}

    @property
    def hc_teu_capacity_by_port(self) -> Dict['Port', HourCounter]:
        return self._hc_teu_capacity_by_port

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    @property
    def q_finish_signals(self) -> 'OrderedSet[Vessel]':
        """Vessels waiting to occupy a berth at this port."""
        return self._q_finish_signals

    def start(self, berth: 'Berth') -> None:
        """
        Berth becomes active (R → S).

        Records berth capacity in port statistics.
        Called when berth enters the idle pool.
        """
        super().start(berth)

        # Statistics - record berth capacity at its port
        port = berth.port
        if port not in self._hc_teu_capacity_by_port:
            self._hc_teu_capacity_by_port[port] = self.add_hour_counter()
        self._hc_teu_capacity_by_port[port].observe_change(1)

        # Note: base class start already fires self._on_start.invoke(entity),
        # so we do NOT call it again. Reference BerthIdle does NOT override start.

    def finish(self, berth: 'Berth') -> None:
        """
        Berth leaves idle state (D → F).

        Removes berth capacity from port statistics.
        Invokes on_finish, which triggers BerthBerthing.RequestStart(berth).
        """
        # Statistics - remove berth capacity
        port = berth.port
        if port in self._hc_teu_capacity_by_port:
            self._hc_teu_capacity_by_port[port].observe_change(-1)

        # Let base class handle D→F transition (+f_hour_counter, on_finish actions)
        super().finish(berth)

    # -------------------------------------------------------------------------
    # Vessel queueing — called by VesselQueuingForBerth.on_start
    # -------------------------------------------------------------------------

    def signal_finish(self, vessel: 'Vessel') -> None:
        """
        External signal that a vessel wants to occupy a berth at its arrival port.

        Called by VesselQueuingForBerth.on_start (wiring: VQB.on_start → BI.signal_finish(vessel)).
        The vessel is queued in q_finish_signals and attempt_finish is scheduled
        to try matching it with an idle berth.
        """
        if vessel is None:
            return
        if vessel not in self._q_finish_signals:
            self._q_finish_signals.add(vessel)
            self._waiting_since_by_vessel[vessel] = self.clock_time
            self.schedule(self.attempt_finish)

    def attempt_finish(self) -> None:
        """
        Try to match queued vessels with idle berths.

        Reference logic (matching the reference behavior BerthIdle.attempt_finish):
          if d_loads_ready_finish.Count == 0 || q_finish_signals.Count == 0: return
          foreach vessel in q_finish_signals.ToList():
            arrivalPort = GetArrivalPortOrThrow(vessel)
            berth = d_loads_ready_finish.FirstOrDefault(b => b.port == arrivalPort)
            if berth == null: continue
            q_finish_signals.Remove(vessel)
            berth.occupying_vessel = vessel
            vessel.current_berth = berth
            finish(berth)
        """
        # Both idle berths (D) and waiting vessels (Q) must be non-empty
        d = self.d_loads_ready_finish
        q = self._q_finish_signals
        if not d or not q:
            return

        for berth in list(d):
            if berth not in d:
                continue
            if not berth.is_available:
                continue

            available_berths = [
                candidate
                for candidate in list(d)
                if candidate.port == berth.port and candidate.is_available
            ]
            waiting_vessels = [
                vessel
                for vessel in list(q)
                if self._get_vessel_arrival_port(vessel) == berth.port
            ]
            if not waiting_vessels:
                continue

            strategy_is_enabled = ENABLE_STRATEGY and self._data_context is not None

            if not strategy_is_enabled:
                vessel = waiting_vessels[0]
            elif (
                len(waiting_vessels)
                >= len(available_berths) * PORT_CONGESTION_MULTIPLIER
            ):
                strategy_arguments = dict(
                    maritime_data_context=self._data_context,
                    port=berth.port,
                    waiting_vessels=waiting_vessels,
                    available_berths=available_berths,
                    current_time=self.clock_time,
                    waiting_since_by_vessel=self._waiting_since_by_vessel,
                )
                vessel = UserStrategy.select_vessel_for_berth(
                    **strategy_arguments
                )
                if vessel is None:
                    vessel = DefaultStrategy.select_vessel_for_berth(
                        **strategy_arguments
                    )
            else:
                vessel = waiting_vessels[0]

            if vessel is None:
                continue
            if vessel not in waiting_vessels:
                raise ValueError(
                    "PortResponseStrategy.select_vessel_for_berth must return "
                    "one of the waiting vessels for the berth's port."
                )

            # Match selected vessel to berth
            q.remove(vessel)
            self._waiting_since_by_vessel.pop(vessel, None)
            berth.occupying_vessel = vessel
            vessel.current_berth = berth

            # Berth transitions D → F
            self.finish(berth)

    def _get_vessel_arrival_port(self, vessel: 'Vessel') -> 'Port':
        """
        Get the port where vessel wants to occupy a berth.

        Reference logic (BerthIdle.GetArrivalPortOrThrow):
          - If vessel.current_segment is null: first segment departure port
          - Else: current segment's arrival port
        """
        if vessel.current_segment is None:
            # Vessel not yet on route — use departure port of first segment
            route = vessel.assigned_service_route
            if route and route.segments:
                first_segment = route.segments[0]
                if first_segment.associated_leg:
                    return first_segment.associated_leg.departure_port
            return None
        else:
            leg = vessel.current_segment.associated_leg
            if leg:
                return leg.arrival_port
            return None

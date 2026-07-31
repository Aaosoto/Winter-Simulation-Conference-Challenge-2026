"""
Vessel Being Served Activity.

Reference behavior: ActivityHandler<Vessel> with:
  - p_start_signals: pending Shipment signals for loading
  - q_finish_signals: pending Berth finish signals
  - signal_start(Shipment): adds to P, schedules attempt_start
  - signal_finish(Berth): adds to Q, schedules attempt_finish
  - attempt_start: for each R vessel, loads shipments, calls start(vessel)
  - attempt_finish: for each Q berth, finds matching D vessel, advances segment

on_start → ShipmentBeingTransported.signal_start(vessel)
           BerthHandlingCargo.signal_start(vessel)
on_finish → VesselSailing.signal_start(vessel)
           ShipmentBeingTransported.signal_finish(vessel)
"""

from typing import TYPE_CHECKING

from o2des.common import ActionSet

from config.simulation_config import ENABLE_STRATEGY
from maritime_data_context.shipment import Shipment as ShipmentClass
from response_strategies.default_strategy import DefaultStrategy
from response_strategies.strategy_validation import (
    capture_alternative_route_strategy_state,
    validate_alternative_route_strategy_result,
)
from response_strategies.user_strategy import UserStrategy

from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet

if TYPE_CHECKING:
    from maritime_data_context import (
        Port, Vessel, Berth, Shipment
    )


class VesselBeingServed(ActivityHandler):
    """
    Represents the activity in which vessels are served at berth.

    start side:
      - Controlled by shipment signals accumulated in p_start_signals.
      - attempt_start matches P shipments to R vessels by route+segment,
        loads them within TEU capacity.
      - Even if no shipment loaded, vessel is started.

    finish side:
      - Controlled by berth signals (q_finish_signals).
      - attempt_finish finds D vessel matching Q berth (v.current_berth == berth),
        discharges shipments, advances to next segment, clears berth.
    """

    def __init__(self, seed: int = 0, data_context=None):
        super().__init__(seed=seed, id="VesselBeingServed")
        self._data_context = data_context

        # Pending shipment signals for loading
        self._p_start_signals: OrderedSet['Shipment'] = OrderedSet()

        # Pending berth signals for finishing
        self._q_finish_signals: OrderedSet['Berth'] = OrderedSet()

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

    @property
    def p_start_signals(self) -> 'OrderedSet[Shipment]':
        return self._p_start_signals

    @property
    def q_finish_signals(self) -> 'OrderedSet[Berth]':
        return self._q_finish_signals

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

# -------------------------------------------------------------------------
    # signal_start / signal_finish — external control gates
    # -------------------------------------------------------------------------

    def _signal_start(self, shipment: 'Shipment') -> None:
        """
        Internal signal: shipment ready for loading consideration.
        Called by SWfL/SWfT on_finish wires (shipment flow).
        """
        if shipment is None:
            return
        if shipment.carrying_vessel is not None:
            return
        if shipment not in self._p_start_signals:
            self._p_start_signals.add(shipment)
            self.schedule(self.attempt_start)

    def signal_start(self, entity) -> None:
        """
        Polymorphic signal entry point (ActivityHandler<T>.signal_start contract).

        Reference dispatch: VBS.signal_start(Shipment) is the custom override;
        base class calls .signal_start(Vessel) from VQB.ConnectTo wiring.

        Python doesn't support method overloading based on argument type,
        so we dispatch based on entity type here.
        """
        if isinstance(entity, ShipmentClass):
            self._signal_start(entity)
            return  # <-- Do NOT call base class; Shipment goes ONLY to p_start_signals
        # Vessel: base class signal_start (adds Vessel to r_loads_requested_start)
        # This is called via VQB.on_finish -> VBS.signal_start(vessel) wiring
        ActivityHandler.signal_start(self, entity)

    def signal_start_shipment(self, shipment: 'Shipment') -> None:
        """Explicit entry point for SWfL/SWfT on_finish wires (shipment flow).

        Reference wiring: SWfL.AO.on_finish.Add(VesselBeingServed.signal_start)
        which calls signal_start(shipment) directly on the VBS instance.
        Using a separate method avoids polymorphic dispatch issues.
        """
        self._signal_start(shipment)

    def signal_finish(self, berth: 'Berth') -> None:
        """Signal that a berth service may finish."""
        if berth is None:
            return
        if berth not in self._q_finish_signals:
            self._q_finish_signals.add(berth)
            self.schedule(self.attempt_finish)

    def attempt_start(self) -> None:
        """
        Reference attempt_start:
          foreach vessel in r_loads_requested_start:
            route = vessel.assigned_service_route
            vesselClass = vessel.vessel_class
            nextSegment = vessel.get_next_segment()
            candidates = p_start_signals filtered by route + nextSequenceIndex
            occupiedTeu = CalculateOccupiedTeu(vessel, route, currentSequenceIndex)
            remaining = teuCapacity - occupiedTeu
            selected = greedy load within remaining
            foreach selected: add to vessel.carried_shipments, remove from P
            start(vessel)
        """
        # Debug: track what gets added to r_loads_requested_start
        for entity in list(self.r_loads_requested_start):
            # Use duck typing: if entity lacks assigned_service_route, it is not a vessel.
            if not hasattr(entity, 'assigned_service_route'):
                continue  # skip Shipments that erroneously entered R
            vessel = entity
            if vessel.assigned_service_route is None:
                raise ValueError(
                    f"Vessel {getattr(vessel, 'index', '?')} has no assigned service route"
                )
            if vessel.vessel_class is None:
                raise ValueError(
                    f"Vessel {getattr(vessel, 'index', '?')} has no vessel class"
                )
            route = vessel.assigned_service_route
            vessel_class = vessel.vessel_class

            current_segment = vessel.current_segment
            next_segment = vessel.get_next_segment()
            next_sequence_index = next_segment.sequence_index

            # Get candidate shipments
            candidates = [
                s for s in self._p_start_signals
                if s.carrying_vessel is None
                and s.get_current_booking().service_route == route
                and s.get_current_booking().departure_segment_index == next_sequence_index
            ]

            # Calculate occupied TEU (exclude dischargeable shipments)
            curr_seq = current_segment.sequence_index if current_segment else None
            occupied_teu = self._calc_occupied_teu(vessel, route, curr_seq)
            remaining = vessel_class.teu_capacity - occupied_teu

            # Greedy load within remaining capacity
            selected = []
            selected_teu = 0
            for s in candidates:
                if selected_teu + s.teu_size <= remaining:
                    selected.append(s)
                    selected_teu += s.teu_size

            for s in selected:
                if s not in vessel.carried_shipments:
                    vessel.carried_shipments.append(s)
                if s.current_storage_port is not None:
                    if s in s.current_storage_port.shipments_in_storage:
                        s.current_storage_port.shipments_in_storage.remove(s)
                    s.current_storage_port = None
                self._p_start_signals.discard(s)

            self.start(vessel)

    def attempt_finish(self) -> None:
        """
        Reference attempt_finish:
          foreach berth in q_finish_signals:
            vessel = d_loads_ready_finish.FirstOrDefault(v => v.current_berth == berth)
            if vessel == null: continue
            Q.Remove(berth)
            discharging = vessel.get_discharging_shipments_at_current_segment()
            foreach: CarriedShipments.Remove
            if CurrentSegment != null: CurrentSegment.current_vessels.Remove(vessel)
            next = vessel.get_next_segment()
            vessel.current_segment = next
            next.current_vessels.Add(vessel)
            vessel.current_berth = null
            finish(vessel)
        """
        for berth in list(self._q_finish_signals):
            vessel = next(
                (v for v in self.d_loads_ready_finish if v.current_berth == berth),
                None
            )
            if vessel is None:
                continue

            self._q_finish_signals.discard(berth)

            # Discharge shipments at current segment
            arrival_port = self._get_vessel_arrival_port(vessel)
            for s in vessel.get_discharging_shipments_at_current_segment():
                if s in vessel.carried_shipments:
                    vessel.carried_shipments.remove(s)
                if arrival_port is not None:
                    s.current_storage_port = arrival_port
                    if s not in arrival_port.shipments_in_storage:
                        arrival_port.shipments_in_storage.append(s)

            self._create_alternative_service_routes_after_cargo_handling(vessel)

            # Advance vessel from current to next segment
            if vessel.current_segment is not None:
                if vessel in vessel.current_segment.current_vessels:
                    vessel.current_segment.current_vessels.remove(vessel)

            next_seg = vessel.get_next_segment()
            vessel.current_segment = next_seg
            next_seg.current_vessels.append(vessel)

            # Release berth
            vessel.current_berth = None

            self.finish(vessel)

    def _create_alternative_service_routes_after_cargo_handling(self, vessel) -> None:
        """Run the route strategy after discharge and before selecting the next leg."""
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

    def _calc_occupied_teu(
        self, vessel: 'Vessel', route, current_seq
    ) -> int:
        """
        Reference CalculateOccupiedTeuBeforeLoading:
          - If currentSeq is null: all carried shipments count
          - Else: exclude those whose booking.arrival_segment_index == currentSeq
        """
        total = 0
        for s in vessel.carried_shipments:
            booking = s.get_current_booking()
            if booking.service_route != route:
                continue
            if current_seq is not None and booking.arrival_segment_index == current_seq:
                continue
            total += s.teu_size
        return total

    def _get_vessel_arrival_port(self, vessel: 'Vessel') -> 'Port':
        if vessel.current_segment is not None:
            leg = vessel.current_segment.associated_leg
            return leg.arrival_port if leg is not None else None

        route = vessel.assigned_service_route
        if route is None or not route.segments:
            return None

        first_segment = sorted(route.segments, key=lambda s: s.sequence_index)[0]
        leg = first_segment.associated_leg
        return leg.departure_port if leg is not None else None

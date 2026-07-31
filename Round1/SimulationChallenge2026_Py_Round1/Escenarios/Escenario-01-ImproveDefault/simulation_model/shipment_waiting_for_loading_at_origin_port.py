"""
Shipment Waiting For Loading At Origin Port Activity.

Reference behavior: ActivityHandler<Shipment> with:
  - No external start/finish gates
  - attempt_finish: for each D shipment, assign booking chain then finish(shipment)
  - start override: record TEU stats
  - depart override: remove TEU stats
  - on_finish -> ConnectTo wires to ShipmentBeingTransported

State flow (base class 4-state machine R->S->D->F):
  signal_start(shipment) -> R -> Schedule(attempt_start)
  attempt_start -> base.start(shipment) -> R->S -> ready_finish(delay=0)
  ready_finish -> S->D -> Schedule(attempt_finish)
  attempt_finish -> assign bookings -> base.finish(shipment) -> D->F, on_finish fires
"""

from dataclasses import dataclass
import datetime as dt
import math
from typing import TYPE_CHECKING, Dict

from o2des.common import ActionSet
from o2des.core import HourCounter

from config.simulation_config import ENABLE_STRATEGY
from maritime_data_context import Booking
from response_strategies.default_strategy import DefaultStrategy
from response_strategies.strategy_validation import (
    capture_alternative_route_strategy_state,
    validate_alternative_route_strategy_result,
)
from response_strategies.user_strategy import UserStrategy

from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet


@dataclass
class _CandidateBookingEdge:
    service_route: object
    departure_port: object
    arrival_port: object
    departure_segment_index: int
    arrival_segment_index: int
    total_distance: float

if TYPE_CHECKING:
    from maritime_data_context import Demand, MaritimeDataContext, Port, Shipment


class ShipmentWaitingForLoadingAtOriginPort(ActivityHandler):
    """
    Represents shipments waiting for loading at their origin port.

    Before a shipment leaves this waiting state, the activity assigns
    a chain of bookings connecting the shipment's origin port to its
    destination port using the configured assignment response_strategies.
    """

    def __init__(self, data_context: 'MaritimeDataContext', seed: int = 0):
        super().__init__(seed=seed, id="ShipmentWaitingForLoadingAtOriginPort")
        self._maritime_data_context = data_context

        # Statistics -- pre-create per-demand and per-port HourCounters so
        # that _creation_time = sim start (= 0), matching the reference behavior's AddHourCounter().
        # Without eager creation, the first shipment to arrive at a port
        # would create the per-port counter late, biasing the per-port TEU
        # average. Per-demand counters are 380 entries (20x19); this is cheap.
        self._hc_teus_by_demand: Dict['Demand', HourCounter] = {
            d: self.add_hour_counter() for d in data_context.demands
        }
        self._hc_teus_by_origin_port: Dict['Port', HourCounter] = {
            p: self.add_hour_counter() for p in data_context.ports
        }

        self._on_finish = ActionSet(object)
        self._booking_assignment_retry_time = None
        self._shipments_waiting_for_booking_retry = OrderedSet()

    @property
    def hc_teus_by_demand(self) -> Dict['Demand', HourCounter]:
        return self._hc_teus_by_demand

    @property
    def hc_teus_by_origin_port(self) -> Dict['Port', HourCounter]:
        return self._hc_teus_by_origin_port

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    # -------------------------------------------------------------------------
    # attempt_finish: assign booking chain, let base finish
    # -------------------------------------------------------------------------

    def attempt_finish(self) -> None:
        """
        Reference attempt_finish:
          foreach shipment in d_loads_ready_finish:
            AssignAssociatedBookings(shipment)
            finish(shipment)
        """
        for shipment in list(self.d_loads_ready_finish):
            if shipment in self._shipments_waiting_for_booking_retry:
                continue
            if self._assign_associated_bookings(shipment):
                self.finish(shipment)
            else:
                if self._schedule_booking_assignment_retry():
                    self._shipments_waiting_for_booking_retry.add(shipment)

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def start(self, shipment: 'Shipment') -> None:
        """Record TEU stats when shipment enters R."""
        super().start(shipment)

        demand = shipment.demand
        if demand not in self._hc_teus_by_demand:
            self._hc_teus_by_demand[demand] = self.add_hour_counter()
        self._hc_teus_by_demand[demand].observe_change(shipment.teu_size)

        origin_port = demand.origin_port
        if origin_port not in self._hc_teus_by_origin_port:
            self._hc_teus_by_origin_port[origin_port] = self.add_hour_counter()
        self._hc_teus_by_origin_port[origin_port].observe_change(shipment.teu_size)

    def depart(self, shipment: 'Shipment') -> None:
        """Remove TEU stats when shipment exits F."""
        if shipment not in self.f_loads_finished:
            return
        super().depart(shipment)

        demand = shipment.demand
        if demand in self._hc_teus_by_demand:
            self._hc_teus_by_demand[demand].observe_change(-shipment.teu_size)

        origin_port = demand.origin_port
        if origin_port in self._hc_teus_by_origin_port:
            self._hc_teus_by_origin_port[origin_port].observe_change(-shipment.teu_size)

    # -------------------------------------------------------------------------
    # Booking chain assignment strategy
    # -------------------------------------------------------------------------

    def _assign_associated_bookings(self, shipment: 'Shipment') -> bool:
        """Allow user-defined initial booking assignment, falling back to default."""
        if not ENABLE_STRATEGY:
            return self._assign_associated_bookings_without_strategy(shipment)

        route_snapshot = capture_alternative_route_strategy_state(
            self._maritime_data_context
        )
        route_decision = UserStrategy.create_alternative_service_routes(
            self._maritime_data_context, self.clock_time
        )
        validate_alternative_route_strategy_result(
            self._maritime_data_context, route_snapshot
        )
        if route_decision is None:
            DefaultStrategy.create_alternative_service_routes(
                self._maritime_data_context, self.clock_time
            )

        user_decision = UserStrategy.assign_associated_bookings(
            self._maritime_data_context, self.clock_time, shipment
        )
        if user_decision is not None:
            return bool(user_decision)

        return DefaultStrategy.assign_associated_bookings(
            self._maritime_data_context, self.clock_time, shipment
        )

    def _assign_associated_bookings_without_strategy(self, shipment: 'Shipment') -> bool:
        """Assign the shortest available booking path without disruption filtering."""
        demand = shipment.demand
        origin_port = demand.origin_port
        destination_port = demand.destination_port

        self._remove_bookings_from_service_routes(shipment.associated_bookings)
        shipment.associated_bookings = []
        shipment.current_booking_index = None

        if origin_port == destination_port:
            return True

        candidate_bookings = self._build_all_candidate_bookings()
        path = self._find_shortest_booking_path(
            origin_port,
            destination_port,
            candidate_bookings,
        )
        if not path:
            return False

        for sequence_index, edge in enumerate(path, start=1):
            booking = Booking(
                sequence_index=sequence_index,
                shipment=shipment,
                service_route=edge.service_route,
                departure_segment_index=edge.departure_segment_index,
                arrival_segment_index=edge.arrival_segment_index,
            )
            shipment.associated_bookings.append(booking)
            edge.service_route.associated_bookings.append(booking)

        shipment.current_booking_index = 1
        return True

    def _build_all_candidate_bookings(self):
        edges = []
        for service_route in self._maritime_data_context.service_routes:
            segments = sorted(
                service_route.segments,
                key=lambda segment: segment.sequence_index,
            )
            segment_count = len(segments)
            for start_index in range(segment_count):
                departure_port = segments[start_index].associated_leg.departure_port
                cumulative_distance = 0.0
                for step in range(1, segment_count):
                    segment_index = (start_index + step - 1) % segment_count
                    leg = segments[segment_index].associated_leg
                    cumulative_distance += leg.sailing_distance
                    arrival_port = leg.arrival_port
                    if departure_port == arrival_port:
                        continue
                    edges.append(
                        _CandidateBookingEdge(
                            service_route=service_route,
                            departure_port=departure_port,
                            arrival_port=arrival_port,
                            departure_segment_index=start_index + 1,
                            arrival_segment_index=segment_index + 1,
                            total_distance=cumulative_distance,
                        )
                    )
        return edges

    def _find_shortest_booking_path(
        self,
        origin_port,
        destination_port,
        candidate_bookings,
    ):
        outgoing = {}
        for edge in candidate_bookings:
            outgoing.setdefault(edge.departure_port, []).append(edge)

        context = self._maritime_data_context
        distances = {port: math.inf for port in context.ports}
        previous_edge = {}
        unvisited = OrderedSet(context.ports)
        distances[origin_port] = 0.0

        while unvisited:
            current = min(unvisited, key=lambda port: distances[port])
            if math.isinf(distances[current]) or current == destination_port:
                break
            unvisited.remove(current)
            for edge in outgoing.get(current, []):
                next_port = edge.arrival_port
                if next_port not in unvisited:
                    continue
                alternative = distances[current] + edge.total_distance
                if alternative < distances[next_port]:
                    distances[next_port] = alternative
                    previous_edge[next_port] = edge

        if destination_port not in previous_edge:
            return None

        path = []
        cursor = destination_port
        while cursor != origin_port:
            edge = previous_edge.get(cursor)
            if edge is None:
                return None
            path.append(edge)
            cursor = edge.departure_port
        path.reverse()
        return path

    @staticmethod
    def _remove_bookings_from_service_routes(bookings) -> None:
        for booking in bookings:
            service_route = booking.service_route
            if service_route is None:
                continue
            while booking in service_route.associated_bookings:
                service_route.associated_bookings.remove(booking)

    def _schedule_booking_assignment_retry(self) -> bool:
        retry_time = self._get_earliest_disruption_recovery_time()
        if retry_time is None:
            return False
        if (
            self._booking_assignment_retry_time is not None
            and self._booking_assignment_retry_time <= retry_time
        ):
            return True

        self._booking_assignment_retry_time = retry_time
        delay = max(retry_time - self.clock_time, dt.timedelta(0))
        self.schedule(self._attempt_finish_after_booking_assignment_retry, delay=delay)
        return True

    def _attempt_finish_after_booking_assignment_retry(self) -> None:
        self._booking_assignment_retry_time = None
        self._shipments_waiting_for_booking_retry.clear()
        self.attempt_finish()

    def _get_earliest_disruption_recovery_time(self):
        retry_times = []
        for plan in self._maritime_data_context.disruption_plans:
            is_close_berth_plan = plan.close_berth and plan.target_berth is not None
            is_congested_leg_plan = plan.multiplier > 1 and plan.target_leg is not None
            if not is_close_berth_plan and not is_congested_leg_plan:
                continue
            if plan.start_offset_days is None or plan.duration_days is None:
                continue

            start = dt.datetime.min + dt.timedelta(days=plan.start_offset_days)
            end = start + dt.timedelta(days=plan.duration_days)
            if start <= self.clock_time < end:
                retry_times.append(end + dt.timedelta(seconds=1))

        return min(retry_times, default=None)

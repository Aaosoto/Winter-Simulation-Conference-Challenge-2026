"""Strategy functions that contestants may modify.

Each function is called by the simulation at a specific decision point. The
``ShippingLineResponseStrategy`` and ``CargoOwnerResponseStrategy`` labels
describe responsibilities, but contestants do not have to keep their logic
strictly separated. When useful, the two response types may be combined. For
example, the logic for ``create_alternative_service_routes`` may instead be
implemented as part of ``adjust_bookings_before_cargo_handling`` so route and
vessel changes are decided together with shipment booking changes.

Two heuristics are implemented below, both aimed at the challenge's sole KPI
(Cumulative Resilience Loss, derived from TEU-weighted Average Transport Time):

1. ``select_vessel_for_berth`` uses Smith's rule (weighted shortest processing
   time first), a single-machine-scheduling result that minimizes total
   TEU-weighted completion time -- exactly what a berth queue is.
2. ``assign_associated_bookings`` extends the plain shortest-distance routing
   with a soft penalty for ports that are currently congested, so cargo
   avoids emerging bottlenecks even before a disruption plan formally closes
   them.
"""

from dataclasses import dataclass
import datetime as dt
import math

from maritime_data_context import Booking
from simulation_model.ordered_set import OrderedSet


# ---------------------------------------------------------------------------
# Tunable heuristic parameters
# ---------------------------------------------------------------------------

# After waiting this many hours, a vessel's berth priority roughly doubles
# regardless of its Smith's-rule score, so a low-priority vessel cannot be
# starved indefinitely by a stream of higher-priority arrivals.
_BERTH_AGING_HOURS = 48.0

# Floor on the estimated cargo-handling duration (hours) used in the Smith's
# rule ratio, so a vessel with (almost) nothing to handle doesn't get an
# unbounded priority score.
_MIN_SERVICE_HOURS = 0.1

# How strongly port congestion inflates the effective sailing distance of an
# edge that arrives there. 1.0 means the most congested port in the network
# roughly doubles the effective distance of using it.
_CONGESTION_WEIGHT = 1.0

# Split between waiting-cargo congestion and berth-occupancy congestion,
# mirroring the GUI's own "Main Risk Port" definition (70% waiting TEU +
# 30% vessels waiting) documented in the WSC 2026 tech document, section 4.2.
_WAITING_TEU_WEIGHT = 0.7
_BERTH_BUSY_WEIGHT = 0.3


@dataclass
class _CandidateEdge:
    service_route: object
    departure_port: object
    arrival_port: object
    departure_segment_index: int
    arrival_segment_index: int
    cost: float


class UserStrategy:
    @staticmethod
    def select_vessel_for_berth(
        maritime_data_context,
        port,
        waiting_vessels,
        available_berths,
        current_time,
        waiting_since_by_vessel=None,
    ):
        """PortResponseStrategy -- Smith's rule (weighted SPT) with aging.

        Smith (1956) proved that, on a single server, sequencing jobs by
        decreasing weight/processing_time minimizes the total weighted
        completion time. A berth is exactly a single server, the "weight" of
        a waiting vessel is the TEU it already carries (every one of those
        TEU keeps accumulating transport time for as long as this vessel
        waits), and its "processing time" is the cargo-handling duration it
        will occupy the berth with once served -- which
        ``simulation_model/berth_handling_cargo.py:_get_duration`` computes as
        ``(discharging_teu + loading_teu) / (quay_crane_count * 45)``, with
        ``quay_crane_count = max(1, int(loa / 55))``. Reusing that exact
        formula here means the priority ranking reflects the real service
        time the vessel is about to consume, not a rough proxy.

        An aging term is layered on top so a vessel with a low Smith ratio
        (small cargo, slow handling) cannot be starved indefinitely by a
        continuous stream of higher-ratio arrivals.
        """
        if not waiting_vessels:
            return None
        waiting_since_by_vessel = waiting_since_by_vessel or {}

        def waiting_hours(vessel):
            waiting_since = waiting_since_by_vessel.get(vessel, current_time)
            return max(0.0, (current_time - waiting_since).total_seconds() / 3600.0)

        def carried_teu(vessel):
            return sum(
                getattr(shipment, "teu_size", 0) or 0
                for shipment in getattr(vessel, "carried_shipments", [])
            )

        def quay_crane_count(vessel):
            vessel_class = getattr(vessel, "vessel_class", None)
            loa = getattr(vessel_class, "loa", 0) or 0
            return max(1, int(loa / 55))

        def handling_workload(vessel):
            try:
                discharging_teu = sum(
                    getattr(shipment, "teu_size", 0) or 0
                    for shipment in vessel.get_discharging_shipments_at_current_segment()
                )
                loading_teu = sum(
                    getattr(shipment, "teu_size", 0) or 0
                    for shipment in vessel.get_loading_shipments_at_next_segment()
                )
                return discharging_teu + loading_teu
            except (AttributeError, TypeError, ValueError):
                return 0.0

        def priority_index(vessel):
            estimated_service_hours = max(
                handling_workload(vessel) / (quay_crane_count(vessel) * 45.0),
                _MIN_SERVICE_HOURS,
            )
            smith_ratio = carried_teu(vessel) / estimated_service_hours
            aging_factor = 1.0 + waiting_hours(vessel) / _BERTH_AGING_HOURS
            return smith_ratio * aging_factor

        return max(
            enumerate(waiting_vessels),
            key=lambda item: (priority_index(item[1]), -item[0]),
        )[1]

    @staticmethod
    def create_alternative_service_routes(context, now, vessel=None):
        """ShippingLineResponseStrategy.

        Return ``None`` to keep the default's reactive behaviour: build a
        disruption-avoiding cyclic route and reserve one vessel for it once a
        disruption is actually active. The congestion-aware routing below
        (``assign_associated_bookings``) already reduces exposure to busy
        ports without needing extra service routes.
        """
        return None

    @staticmethod
    def assign_associated_bookings(context, now, shipment) -> bool:
        """CargoOwnerResponseStrategy -- congestion-aware shortest path.

        Builds the same kind of multi-hop candidate edges as the reference
        implementation (any departure segment on any service route, extended
        forward around the route's cycle), with two differences:

        1. Hard constraints are unchanged: ports/legs under an *active*
           disruption plan are excluded outright, exactly like the default.
        2. Soft constraint (new): every candidate edge's cost is its sailing
           distance multiplied by a congestion factor of its arrival port,
           where congestion combines currently-waiting cargo TEU
           (``port.shipments_in_storage``) and berth occupancy -- the same
           two signals the GUI uses for "Main Risk Port", weighted the same
           70/30 way. This steers new shipments away from ports that are
           becoming a bottleneck even before any formal disruption plan
           closes them, which a pure shortest-distance search cannot see.
        """
        demand = shipment.demand
        origin_port = demand.origin_port
        destination_port = demand.destination_port

        _clear_bookings(shipment)

        if origin_port == destination_port:
            return True

        avoid_port_names, congested_legs = _active_hard_constraints(context, now)
        if destination_port.name.casefold() in avoid_port_names:
            return False

        congestion_multipliers = _congestion_multipliers(context)
        edges = _build_candidate_edges(
            context, avoid_port_names, congested_legs, congestion_multipliers
        )
        path = _shortest_path(context, origin_port, destination_port, edges)
        if not path:
            return False

        _apply_path_as_bookings(shipment, path)
        return True

    @staticmethod
    def adjust_bookings_before_cargo_handling(context, now, vessel) -> None:
        """CargoOwnerResponseStrategy.

        Return ``None`` to keep the default's in-transit replanning, which
        only reroutes a carried shipment when an *active* disruption actually
        affects the unfinished part of its current route. Driving this
        decision purely off the same live congestion signal used above would
        make already-committed cargo flip-flop between ports as queues rise
        and fall within a single simulated day, which is more likely to hurt
        ATT than help it.
        """
        return None


# ---------------------------------------------------------------------------
# Helpers -- hard (disruption) constraints
# ---------------------------------------------------------------------------

def _plan_active(plan, now) -> bool:
    if plan.start_offset_days is None or plan.duration_days is None:
        return False
    start = dt.datetime.min + dt.timedelta(days=plan.start_offset_days)
    end = start + dt.timedelta(days=plan.duration_days)
    return start <= now < end


def _active_hard_constraints(context, now):
    """Ports/legs that are currently under an active disruption plan."""
    avoid_port_names = OrderedSet()
    congested_legs = OrderedSet()
    for plan in context.disruption_plans:
        if not _plan_active(plan, now):
            continue
        if plan.close_berth and plan.target_berth is not None:
            avoid_port_names.add(plan.target_berth.port.name.casefold())
        if plan.multiplier > 1 and plan.target_leg is not None:
            congested_legs.add(plan.target_leg)
    return avoid_port_names, congested_legs


def _leg_key(leg):
    return (leg.departure_port.name.casefold(), leg.arrival_port.name.casefold())


def _disruption_key(avoid_port_names, congested_legs):
    return (
        tuple(sorted(avoid_port_names)),
        tuple(sorted(_leg_key(leg) for leg in congested_legs)),
    )


def _route_is_available(route, disruption_key) -> bool:
    """Mirrors DefaultStrategy's own filter for alternative routes:

    an alternative route (created reactively when a disruption is active)
    is only usable while its disruption profile still matches the current
    one and it actually has vessels deployed on it.
    """
    if route.source_service_route is None:
        return True
    if route.disruption_key != disruption_key:
        return False
    return bool(route.deployed_vessels)


# ---------------------------------------------------------------------------
# Helpers -- soft (congestion) cost
# ---------------------------------------------------------------------------

def _port_congestion_raw(port):
    waiting_teu = sum(
        getattr(shipment, "teu_size", 0) or 0
        for shipment in port.shipments_in_storage
    )
    berths = port.berths
    busy = sum(
        1 for berth in berths if not berth.is_available or berth.occupying_vessel is not None
    )
    busy_fraction = (busy / len(berths)) if berths else 0.0
    return waiting_teu, busy_fraction


def _congestion_multipliers(context):
    """Return {port: distance_multiplier}, normalized across the network."""
    raw = {port: _port_congestion_raw(port) for port in context.ports}
    max_waiting_teu = max((waiting for waiting, _ in raw.values()), default=0.0) or 1.0

    multipliers = {}
    for port, (waiting_teu, busy_fraction) in raw.items():
        congestion_score = (
            _WAITING_TEU_WEIGHT * (waiting_teu / max_waiting_teu)
            + _BERTH_BUSY_WEIGHT * busy_fraction
        )
        multipliers[port] = 1.0 + _CONGESTION_WEIGHT * congestion_score
    return multipliers


def _build_candidate_edges(context, avoid_port_names, congested_legs, congestion_multipliers):
    disruption_key = _disruption_key(avoid_port_names, congested_legs)
    edges = []
    for route in context.service_routes:
        if not _route_is_available(route, disruption_key):
            continue
        segments = sorted(route.segments, key=lambda segment: segment.sequence_index)
        segment_count = len(segments)
        if segment_count == 0:
            continue

        for start_index in range(segment_count):
            departure_port = segments[start_index].associated_leg.departure_port
            cumulative_distance = 0.0
            for step in range(1, segment_count):
                segment_index = (start_index + step - 1) % segment_count
                leg = segments[segment_index].associated_leg
                cumulative_distance += leg.sailing_distance
                arrival_port = leg.arrival_port

                if arrival_port.name.casefold() in avoid_port_names or departure_port == arrival_port:
                    continue

                candidate_segments = [
                    segments[(start_index + offset) % segment_count]
                    for offset in range(step)
                ]
                if any(segment.associated_leg in congested_legs for segment in candidate_segments):
                    continue

                intermediate_ports = [
                    segment.associated_leg.arrival_port for segment in candidate_segments
                ]
                if any(port.name.casefold() in avoid_port_names for port in intermediate_ports[:-1]):
                    continue

                cost = cumulative_distance * congestion_multipliers.get(arrival_port, 1.0)
                edges.append(
                    _CandidateEdge(
                        route,
                        departure_port,
                        arrival_port,
                        start_index + 1,
                        segment_index + 1,
                        cost,
                    )
                )
    return edges


def _shortest_path(context, origin_port, destination_port, edges):
    outgoing = {}
    for edge in edges:
        outgoing.setdefault(edge.departure_port, []).append(edge)

    distances = {port: math.inf for port in context.ports}
    previous_edge = {}
    unvisited = OrderedSet(context.ports)
    distances[origin_port] = 0.0

    while unvisited:
        current = min(unvisited, key=lambda port: distances[port])
        if math.isinf(distances[current]) or current is destination_port:
            break
        unvisited.remove(current)
        for edge in outgoing.get(current, []):
            next_port = edge.arrival_port
            if next_port not in unvisited:
                continue
            alternative = distances[current] + edge.cost
            if alternative < distances[next_port]:
                distances[next_port] = alternative
                previous_edge[next_port] = edge

    if destination_port not in previous_edge:
        return None

    path = []
    cursor = destination_port
    while cursor is not origin_port:
        edge = previous_edge.get(cursor)
        if edge is None:
            return None
        path.append(edge)
        cursor = edge.departure_port
    path.reverse()
    return path


# ---------------------------------------------------------------------------
# Helpers -- booking application
# ---------------------------------------------------------------------------

def _clear_bookings(shipment):
    for booking in shipment.associated_bookings:
        service_route = booking.service_route
        if service_route is None:
            continue
        while booking in service_route.associated_bookings:
            service_route.associated_bookings.remove(booking)
    shipment.associated_bookings = []
    shipment.current_booking_index = None


def _apply_path_as_bookings(shipment, path):
    for index, edge in enumerate(path):
        booking = Booking(
            sequence_index=index + 1,
            shipment=shipment,
            service_route=edge.service_route,
            departure_segment_index=edge.departure_segment_index,
            arrival_segment_index=edge.arrival_segment_index,
        )
        shipment.associated_bookings.append(booking)
        edge.service_route.associated_bookings.append(booking)
    shipment.current_booking_index = min(
        booking.sequence_index for booking in shipment.associated_bookings
    )

"""Default disruption-aware shipment rerouting strategy."""

from dataclasses import dataclass
import datetime as dt
import math

from maritime_data_context import Booking, Segment, ServiceRoute
from simulation_model.disruption_status import is_disruption_active
from simulation_model.ordered_set import OrderedSet


@dataclass
class _CandidateBookingEdge:
    service_route: object
    departure_port: object
    arrival_port: object
    departure_segment_index: int
    arrival_segment_index: int
    total_distance: float


class DefaultStrategy:
    @staticmethod
    def select_vessel_for_berth(
        maritime_data_context,
        port,
        waiting_vessels,
        available_berths,
        current_time,
        waiting_since_by_vessel=None,
    ):
        """PortResponseStrategy.

        Select which waiting vessel should receive an available berth.

        Contestants can edit this method to decide port congestion priorities.
        The default policy uses a normalized hybrid score:
        40% waiting time, 30% carried TEU, 20% vessel capacity, and a 10%
        penalty for expected cargo-handling workload. Ties are resolved by
        waiting-queue order.
        """
        if not waiting_vessels:
            return None
        waiting_since_by_vessel = waiting_since_by_vessel or {}

        def waiting_hours(vessel):
            waiting_since = waiting_since_by_vessel.get(vessel, current_time)
            return max(
                0.0,
                (current_time - waiting_since).total_seconds() / 3600.0,
            )

        def carried_teu(vessel):
            return sum(
                getattr(shipment, "teu_size", 0) or 0
                for shipment in getattr(vessel, "carried_shipments", [])
            )

        def vessel_capacity(vessel):
            vessel_class = getattr(vessel, "vessel_class", None)
            return getattr(vessel_class, "teu_capacity", 0) or 0

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
                return 0

        def normalize(values):
            minimum = min(values)
            maximum = max(values)
            if maximum == minimum:
                return [0.0] * len(values)
            span = maximum - minimum
            return [(value - minimum) / span for value in values]

        waiting_scores = normalize([waiting_hours(vessel) for vessel in waiting_vessels])
        carried_scores = normalize([carried_teu(vessel) for vessel in waiting_vessels])
        capacity_scores = normalize([vessel_capacity(vessel) for vessel in waiting_vessels])
        handling_scores = normalize([handling_workload(vessel) for vessel in waiting_vessels])

        priority_scores = [
            0.4 * waiting_score
            + 0.3 * carried_score
            + 0.2 * capacity_score
            - 0.1 * handling_score
            for waiting_score, carried_score, capacity_score, handling_score in zip(
                waiting_scores,
                carried_scores,
                capacity_scores,
                handling_scores,
            )
        ]

        return max(
            enumerate(waiting_vessels),
            key=lambda item: (priority_scores[item[0]], -item[0]),
        )[1]

    @staticmethod
    def create_alternative_service_routes(context, now, vessel=None):
        """ShippingLineResponseStrategy.

        Build disruption-avoiding cyclic routes from existing legs and reserve
        one vessel from each affected original route. A reserved vessel switches
        only when it arrives empty at the alternative route's start port.
        """
        _restore_inactive_alternative_route_vessels(context, now, vessel)
        if not is_disruption_active(context, now):
            return
        _ensure_alternative_service_routes(context, now)
        _try_switch_empty_vessel_to_pending_route(vessel)

    @staticmethod
    def assign_associated_bookings(context, now, shipment) -> bool:
        """CargoOwnerResponseStrategy.

        Assign the initial booking chain for a shipment at its origin port.

        The shipment's existing bookings are cleared, then the shortest path from
        demand origin to demand destination is built. If any active close-berth or
        congested-leg disruption exists, the strategy builds a path that avoids
        the corresponding ports and legs. If no filtered path exists, it returns
        False so the caller can keep the shipment waiting and retry later.
        """
        demand = shipment.demand
        origin_port = demand.origin_port
        destination_port = demand.destination_port

        _remove_bookings_from_service_routes(shipment.associated_bookings)
        shipment.associated_bookings = []
        shipment.current_booking_index = None

        if origin_port == destination_port:
            return True

        avoid_port_names = OrderedSet()
        congested_legs = OrderedSet()
        if is_disruption_active(context, now):
            close_berth_plans, congested_leg_plans = _get_active_disruption_plans(
                context, now
            )
            avoid_port_names = _get_avoid_port_names(close_berth_plans)
            congested_legs = _get_congested_legs(congested_leg_plans)

        candidate_bookings = _build_all_candidate_bookings(
            context, avoid_port_names, congested_legs
        )
        path = None
        if destination_port.name.casefold() not in avoid_port_names:
            path = _find_shortest_booking_path(
                context, origin_port, destination_port, candidate_bookings
            )

        if not path:
            return False

        for i, edge in enumerate(path):
            booking = Booking(
                sequence_index=i + 1,
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
        return True

    @staticmethod
    def adjust_bookings_before_cargo_handling(context, now, vessel) -> None:
        """CargoOwnerResponseStrategy.

        Replan carried shipments after a vessel reaches port but before cargo handling.

        This is the only in-transit booking-replanning decision point. It handles
        both an unfinished current booking and disruptions found only in later
        bookings after the current segment reaches the booking's arrival segment.

        For each carried shipment, the completed portion of the current booking is
        retained up to the vessel's current arrival port. If the unfinished portion
        of the current booking or later bookings contains active avoid ports or
        congested legs, the remaining path from the current port to the shipment's
        final destination is rebuilt while avoiding only the disruption types that
        affect that unfinished portion.

        When the first new booking uses the same route as the completed current
        booking, the two pieces are merged into one booking. Otherwise the current
        booking is shortened to end at the current port, causing the shipment to be
        discharged here and wait for another route.
        """
        if not is_disruption_active(context, now):
            return

        close_berth_plans, congested_leg_plans = _get_active_disruption_plans(context, now)
        if not close_berth_plans and not congested_leg_plans:
            return

        current_segment = vessel.current_segment
        if current_segment is None:
            return

        current_port = current_segment.associated_leg.arrival_port
        if current_port is None:
            return

        avoid_port_names = _get_avoid_port_names(close_berth_plans)
        congested_legs = _get_congested_legs(congested_leg_plans)

        for shipment in list(vessel.carried_shipments):
            try:
                current_booking = shipment.get_current_booking()
            except ValueError:
                continue

            final_port = _get_final_booking_port(shipment)
            if final_port is None or final_port.name.casefold() in avoid_port_names:
                continue

            has_avoid_port, has_congested_leg = _get_unfinished_booking_impacts(
                shipment,
                current_booking,
                current_segment,
                avoid_port_names,
                congested_legs,
            )
            if not has_avoid_port and not has_congested_leg:
                continue

            path = _find_shortest_booking_path(
                context,
                current_port,
                final_port,
                _build_all_candidate_bookings(
                    context,
                    avoid_port_names if has_avoid_port else OrderedSet(),
                    congested_legs if has_congested_leg else OrderedSet(),
                ),
            )
            if not path:
                continue

            _replace_unfinished_bookings_from_current_port(
                shipment, current_booking, current_segment, path
            )

def _is_active(plan, now) -> bool:
    if plan.start_offset_days is None or plan.duration_days is None:
        return False
    start = dt.datetime.min + dt.timedelta(days=plan.start_offset_days)
    end = start + dt.timedelta(days=plan.duration_days)
    return start <= now < end


def _get_active_disruption_plans(context, now):
    close_berth_plans = [
        plan for plan in context.disruption_plans
        if plan.close_berth and _is_active(plan, now)
    ]
    congested_leg_plans = [
        plan for plan in context.disruption_plans
        if plan.multiplier > 1 and _is_active(plan, now)
    ]
    return close_berth_plans, congested_leg_plans


def _get_avoid_port_names(close_berth_plans):
    return OrderedSet(
        plan.target_berth.port.name.casefold()
        for plan in close_berth_plans
        if plan.target_berth is not None
    )


def _get_congested_legs(congested_leg_plans):
    return OrderedSet(
        plan.target_leg
        for plan in congested_leg_plans
        if plan.target_leg is not None
    )


def _get_active_disruption_key(context, now):
    close_berth_plans, congested_leg_plans = _get_active_disruption_plans(context, now)
    avoid_port_names = _get_avoid_port_names(close_berth_plans)
    congested_leg_keys = OrderedSet(
        _leg_key(plan.target_leg)
        for plan in congested_leg_plans
        if plan.target_leg is not None
    )
    return (
        tuple(sorted(avoid_port_names)),
        tuple(sorted(congested_leg_keys)),
    )


def _ensure_alternative_service_routes(context, now):
    close_berth_plans, congested_leg_plans = _get_active_disruption_plans(context, now)
    avoid_port_names = _get_avoid_port_names(close_berth_plans)
    congested_leg_keys = OrderedSet(
        _leg_key(plan.target_leg)
        for plan in congested_leg_plans
        if plan.target_leg is not None
    )
    if not avoid_port_names and not congested_leg_keys:
        return []

    disruption_key = (
        tuple(sorted(avoid_port_names)),
        tuple(sorted(congested_leg_keys)),
    )
    alternatives = []
    for source_route in list(context.initial_service_routes):
        if not _service_route_is_disrupted(
            source_route, avoid_port_names, congested_leg_keys
        ):
            continue

        alternative_route = next(
            (
                route
                for route in context.service_routes
                if route.source_service_route is source_route
                and route.disruption_key == disruption_key
            ),
            None,
        )
        if alternative_route is None:
            alternative_route = _build_alternative_service_route(
                context,
                source_route,
                avoid_port_names,
                congested_leg_keys,
                disruption_key,
            )
        if alternative_route is None:
            continue

        _reserve_one_vessel_for_alternative_route(
            context, source_route, alternative_route
        )
        alternatives.append(alternative_route)

    return alternatives


def _service_route_is_disrupted(route, avoid_port_names, congested_leg_keys):
    for segment in route.segments:
        leg = segment.associated_leg
        if _leg_key(leg) in congested_leg_keys:
            return True
        if (
            leg.departure_port.name.casefold() in avoid_port_names
            or leg.arrival_port.name.casefold() in avoid_port_names
        ):
            return True
    return False


def _restore_inactive_alternative_route_vessels(context, now, vessel=None):
    vessels = [vessel] if vessel is not None else list(context.vessels)
    restored = False
    active_disruption_key = _get_active_disruption_key(context, now)

    for current_vessel in vessels:
        if current_vessel is None:
            continue
        pending_route = current_vessel.pending_assigned_service_route
        if (
            pending_route is not None
            and pending_route.source_service_route is not None
            and pending_route.disruption_key != active_disruption_key
        ):
            current_vessel.pending_assigned_service_route = None

        assigned_route = current_vessel.assigned_service_route
        if (
            assigned_route is None
            or assigned_route.source_service_route is None
            or assigned_route.disruption_key == active_disruption_key
        ):
            continue
        restored = _try_switch_empty_vessel_to_source_route(current_vessel) or restored

    return restored


def _build_alternative_service_route(
    context,
    source_route,
    avoid_port_names,
    congested_leg_keys,
    disruption_key,
):
    source_segments = sorted(
        source_route.segments, key=lambda segment: segment.sequence_index
    )
    anchor_ports = []
    for segment in source_segments:
        port = segment.associated_leg.departure_port
        if port.name.casefold() in avoid_port_names:
            continue
        if not anchor_ports or anchor_ports[-1] is not port:
            anchor_ports.append(port)

    if len(anchor_ports) < 2:
        return None

    route_legs = []
    for index, departure_port in enumerate(anchor_ports):
        arrival_port = anchor_ports[(index + 1) % len(anchor_ports)]
        leg_path = _find_shortest_leg_path(
            context,
            departure_port,
            arrival_port,
            avoid_port_names,
            congested_leg_keys,
        )
        if not leg_path:
            return None
        route_legs.extend(leg_path)

    route_id = _next_alternative_route_id(context, source_route.id)
    route = ServiceRoute(
        id=route_id,
        name=f"{source_route.name} Disruption Alternative",
        start_day_of_week=source_route.start_day_of_week,
    )
    route.source_service_route = source_route
    route.disruption_key = disruption_key
    for sequence_index, leg in enumerate(route_legs, start=1):
        segment = Segment(sequence_index, leg, route)
        route.segments.append(segment)
        leg.segments.append(segment)
        context.partial_service_routes.append(segment)

    context.service_routes.append(route)
    return route


def _next_alternative_route_id(context, source_route_id):
    existing_ids = OrderedSet(route.id.casefold() for route in context.service_routes)
    index = 1
    while True:
        route_id = f"{source_route_id}-ALT-{index}"
        if route_id.casefold() not in existing_ids:
            return route_id
        index += 1


def _find_shortest_leg_path(
    context,
    origin_port,
    destination_port,
    avoid_port_names,
    congested_leg_keys,
):
    outgoing = {}
    for leg in context.legs:
        if _leg_key(leg) in congested_leg_keys:
            continue
        if (
            leg.departure_port.name.casefold() in avoid_port_names
            or leg.arrival_port.name.casefold() in avoid_port_names
        ):
            continue
        outgoing.setdefault(leg.departure_port, []).append(leg)

    distances = {port: math.inf for port in context.ports}
    previous_leg = {}
    unvisited = OrderedSet(context.ports)
    distances[origin_port] = 0.0

    while unvisited:
        current = min(unvisited, key=lambda port: distances[port])
        if math.isinf(distances[current]) or current is destination_port:
            break
        unvisited.remove(current)
        for leg in outgoing.get(current, []):
            next_port = leg.arrival_port
            if next_port not in unvisited:
                continue
            alternative = distances[current] + leg.sailing_distance
            if alternative < distances[next_port]:
                distances[next_port] = alternative
                previous_leg[next_port] = leg

    if destination_port not in previous_leg:
        return None

    path = []
    cursor = destination_port
    while cursor is not origin_port:
        leg = previous_leg.get(cursor)
        if leg is None:
            return None
        path.append(leg)
        cursor = leg.departure_port
    path.reverse()
    return path


def _reserve_one_vessel_for_alternative_route(
    context, source_route, alternative_route
):
    if any(
        vessel.assigned_service_route is alternative_route
        or vessel.pending_assigned_service_route is alternative_route
        for vessel in context.vessels
    ):
        return

    candidates = sorted(source_route.deployed_vessels, key=lambda vessel: vessel.index)
    for vessel in candidates:
        if vessel.assigned_service_route is not source_route:
            continue
        if vessel.pending_assigned_service_route is not None:
            continue
        vessel.pending_assigned_service_route = alternative_route
        return


def _try_switch_empty_vessel_to_pending_route(vessel):
    if vessel is None or vessel.carried_shipments:
        return False

    pending_route = vessel.pending_assigned_service_route
    if pending_route is None or not pending_route.segments:
        return False

    current_port = None
    current_segment = vessel.current_segment
    if current_segment is not None and current_segment.associated_leg is not None:
        current_port = current_segment.associated_leg.arrival_port
    elif vessel.current_berth is not None:
        current_port = vessel.current_berth.port

    first_segment = min(
        pending_route.segments, key=lambda segment: segment.sequence_index
    )
    start_port = first_segment.associated_leg.departure_port
    if current_port is not start_port:
        return False

    old_route = vessel.assigned_service_route
    if current_segment is not None:
        while vessel in current_segment.current_vessels:
            current_segment.current_vessels.remove(vessel)
    if old_route is not None:
        while vessel in old_route.deployed_vessels:
            old_route.deployed_vessels.remove(vessel)
    if vessel not in pending_route.deployed_vessels:
        pending_route.deployed_vessels.append(vessel)

    vessel.assigned_service_route = pending_route
    vessel.pending_assigned_service_route = None
    vessel.current_segment = None
    return True


def _try_switch_empty_vessel_to_source_route(vessel):
    if vessel is None or vessel.carried_shipments:
        return False

    alternative_route = vessel.assigned_service_route
    if alternative_route is None or alternative_route.source_service_route is None:
        return False

    source_route = alternative_route.source_service_route
    current_port = _get_vessel_current_port(vessel)
    if current_port is None:
        return False

    reentry_segment = _find_reentry_segment(source_route, current_port)
    if reentry_segment is None:
        return False

    current_segment = vessel.current_segment
    if current_segment is not None:
        while vessel in current_segment.current_vessels:
            current_segment.current_vessels.remove(vessel)
    while vessel in alternative_route.deployed_vessels:
        alternative_route.deployed_vessels.remove(vessel)
    if vessel not in source_route.deployed_vessels:
        source_route.deployed_vessels.append(vessel)

    vessel.assigned_service_route = source_route
    vessel.pending_assigned_service_route = None
    vessel.current_segment = reentry_segment
    if vessel not in reentry_segment.current_vessels:
        reentry_segment.current_vessels.append(vessel)
    return True


def _get_vessel_current_port(vessel):
    current_segment = vessel.current_segment
    if current_segment is not None and current_segment.associated_leg is not None:
        return current_segment.associated_leg.arrival_port
    if vessel.current_berth is not None:
        return vessel.current_berth.port
    return None


def _find_reentry_segment(route, current_port):
    segments = sorted(route.segments, key=lambda segment: segment.sequence_index)
    for segment in segments:
        leg = segment.associated_leg
        if leg is not None and leg.arrival_port is current_port:
            return segment
    for segment in segments:
        leg = segment.associated_leg
        if leg is not None and leg.departure_port is current_port:
            return None
    return None


def _leg_key(leg):
    return (
        leg.departure_port.name.casefold(),
        leg.arrival_port.name.casefold(),
    )


def _get_unfinished_booking_impacts(
    shipment, current_booking, current_segment, avoid_port_names, congested_legs
):
    if not avoid_port_names and not congested_legs:
        return False, False

    has_avoid_port = False
    has_congested_leg = False

    for booking in sorted(shipment.associated_bookings, key=lambda b: b.sequence_index):
        if booking.sequence_index < current_booking.sequence_index:
            continue
        if booking.service_route is None:
            continue

        segments = sorted(booking.service_route.segments, key=lambda s: s.sequence_index)
        if not segments:
            continue

        if booking is current_booking:
            current_index = _find_segment_list_index(segments, current_segment.sequence_index)
            end_index = _find_segment_list_index(segments, booking.arrival_segment_index)
            if current_index >= 0 and current_index == end_index:
                continue
            if current_index < 0:
                start_index = _find_segment_list_index(segments, booking.departure_segment_index)
            else:
                start_index = (current_index + 1) % len(segments)
        else:
            start_index = _find_segment_list_index(segments, booking.departure_segment_index)

        end_index = _find_segment_list_index(segments, booking.arrival_segment_index)
        if start_index < 0 or end_index < 0:
            continue

        for segment in _iter_segments_between(segments, start_index, end_index):
            leg = segment.associated_leg
            if leg.arrival_port.name.casefold() in avoid_port_names:
                has_avoid_port = True
            if leg in congested_legs:
                has_congested_leg = True
            if has_avoid_port and has_congested_leg:
                return True, True

    return has_avoid_port, has_congested_leg


def _replace_unfinished_bookings_from_current_port(
    shipment, current_booking, current_segment, path
):
    original_bookings = list(shipment.associated_bookings)
    retained = sorted(
        (
            booking
            for booking in shipment.associated_bookings
            if booking.sequence_index < current_booking.sequence_index
        ),
        key=lambda booking: booking.sequence_index,
    )

    completed_booking = current_booking
    completed_booking.arrival_segment_index = current_segment.sequence_index

    next_sequence = current_booking.sequence_index + 1
    new_bookings = []
    first_edge = path[0]
    if first_edge.service_route is completed_booking.service_route:
        completed_booking.arrival_segment_index = first_edge.arrival_segment_index
        remaining_edges = path[1:]
    else:
        remaining_edges = path

    for edge in remaining_edges:
        booking = Booking(
            sequence_index=next_sequence,
            shipment=shipment,
            service_route=edge.service_route,
            departure_segment_index=edge.departure_segment_index,
            arrival_segment_index=edge.arrival_segment_index,
        )
        new_bookings.append(booking)
        next_sequence += 1

    retained_bookings = retained + [completed_booking]
    replaced_bookings = [
        booking for booking in original_bookings if booking not in retained_bookings
    ]
    _remove_bookings_from_service_routes(replaced_bookings)
    for booking in new_bookings:
        booking.service_route.associated_bookings.append(booking)
    shipment.associated_bookings.clear()
    shipment.associated_bookings.extend(retained_bookings + new_bookings)
    shipment.current_booking_index = completed_booking.sequence_index


def _remove_bookings_from_service_routes(bookings):
    """Remove stale reverse references for bookings no longer owned by a shipment."""
    for booking in bookings:
        service_route = booking.service_route
        if service_route is None:
            continue
        while booking in service_route.associated_bookings:
            service_route.associated_bookings.remove(booking)


def _get_final_booking_port(shipment):
    last_booking = max(shipment.associated_bookings, key=lambda b: b.sequence_index, default=None)
    if last_booking is None or last_booking.service_route is None:
        return None

    final_segment = next(
        (
            segment
            for segment in last_booking.service_route.segments
            if segment.sequence_index == last_booking.arrival_segment_index
        ),
        None,
    )
    return final_segment.associated_leg.arrival_port if final_segment else None


def _find_segment_list_index(segments, sequence_index):
    return next(
        (
            index
            for index, segment in enumerate(segments)
            if segment.sequence_index == sequence_index
        ),
        -1,
    )


def _iter_segments_between(segments, start_index, end_index):
    cursor = start_index
    while True:
        yield segments[cursor]
        if cursor == end_index:
            break
        cursor = (cursor + 1) % len(segments)


def _build_all_candidate_bookings(context, avoid_port_names, congested_legs=None):
    congested_legs = congested_legs or OrderedSet()
    disruption_key = (
        tuple(sorted(avoid_port_names)),
        tuple(sorted(_leg_key(leg) for leg in congested_legs)),
    )
    edges = []
    for service_route in context.service_routes:
        if not _route_is_available_for_booking(service_route, disruption_key):
            continue
        segments = sorted(service_route.segments, key=lambda segment: segment.sequence_index)
        segment_count = len(segments)
        for start_index in range(segment_count):
            cumulative_distance = 0.0
            departure_port = segments[start_index].associated_leg.departure_port
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
                    segment.associated_leg.arrival_port
                    for segment in candidate_segments
                ]
                if any(port.name.casefold() in avoid_port_names for port in intermediate_ports[:-1]):
                    continue
                edges.append(
                    _CandidateBookingEdge(
                        service_route,
                        departure_port,
                        arrival_port,
                        start_index + 1,
                        segment_index + 1,
                        cumulative_distance,
                    )
                )
    return edges


def _route_is_available_for_booking(route, disruption_key):
    if route.source_service_route is None:
        return True
    if route.disruption_key != disruption_key:
        return False
    return bool(route.deployed_vessels)


def _find_shortest_booking_path(context, origin_port, destination_port, all_edges):
    outgoing = {}
    for edge in all_edges:
        outgoing.setdefault(edge.departure_port, []).append(edge)

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

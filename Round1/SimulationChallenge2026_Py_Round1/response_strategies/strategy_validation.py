"""Validation helpers for contestant-defined response strategies."""

from simulation_model.ordered_set import OrderedSet


def capture_alternative_route_strategy_state(context):
    """Capture identities and assignments that the strategy must preserve."""
    return {
        "vessels": tuple(context.vessels),
        "legs": tuple(context.legs),
        "service_routes": tuple(context.service_routes),
        "assigned_routes": {
            vessel: vessel.assigned_service_route for vessel in context.vessels
        },
    }


def validate_alternative_route_strategy_result(context, snapshot) -> None:
    """Reject new legs/vessels and invalid vessel transfers to new routes."""
    original_vessels = OrderedSet(snapshot["vessels"])
    current_vessels = OrderedSet(context.vessels)
    if (
        len(context.vessels) != len(snapshot["vessels"])
        or current_vessels != original_vessels
    ):
        raise ValueError(
            "create_alternative_service_routes must not add, remove, or replace "
            "vessels; context.vessels must remain unchanged."
        )

    original_legs = OrderedSet(snapshot["legs"])
    current_legs = OrderedSet(context.legs)
    if len(context.legs) != len(snapshot["legs"]) or current_legs != original_legs:
        raise ValueError(
            "create_alternative_service_routes must not add, remove, or replace "
            "legs; new routes must use existing context.legs."
        )

    original_routes = OrderedSet(snapshot["service_routes"])
    new_routes = [
        route for route in context.service_routes if route not in original_routes
    ]
    new_route_set = OrderedSet(new_routes)
    for route in new_routes:
        _validate_new_route(route, original_legs)

    original_assignments = snapshot["assigned_routes"]
    for vessel in context.vessels:
        assigned_route = vessel.assigned_service_route
        pending_route = vessel.pending_assigned_service_route
        for target_route in (assigned_route, pending_route):
            if target_route not in new_route_set:
                continue
            original_route = original_assignments[vessel]
            if original_route is None or original_route not in original_routes:
                raise ValueError(
                    "A vessel assigned to a newly created service route must "
                    "come from a service route that existed before the strategy call."
                )

        if assigned_route in new_route_set and vessel not in assigned_route.deployed_vessels:
            raise ValueError(
                "A vessel assigned to a new service route must also be registered "
                "in that route's deployed_vessels collection."
            )

    for route in new_routes:
        for vessel in route.deployed_vessels:
            if vessel not in original_vessels:
                raise ValueError(
                    "New service routes may deploy only vessels that existed before "
                    "the strategy call."
                )
            original_route = original_assignments[vessel]
            if original_route is None or original_route not in original_routes:
                raise ValueError(
                    "A vessel deployed on a new service route must be transferred "
                    "from a pre-existing service route."
                )


def _validate_new_route(route, original_legs) -> None:
    segments = sorted(route.segments, key=lambda segment: segment.sequence_index)
    if not segments:
        raise ValueError("A newly created service route must contain segments.")

    expected_indexes = list(range(1, len(segments) + 1))
    if [segment.sequence_index for segment in segments] != expected_indexes:
        raise ValueError(
            "A newly created service route must have consecutive segment indexes."
        )

    for index, segment in enumerate(segments):
        if segment.associated_service_route is not route:
            raise ValueError(
                "Every segment in a new service route must reference that route."
            )
        if segment.associated_leg not in original_legs:
            raise ValueError(
                "A newly created service route must use only legs that existed "
                "before the strategy call."
            )
        next_segment = segments[(index + 1) % len(segments)]
        if (
            segment.associated_leg.arrival_port
            is not next_segment.associated_leg.departure_port
        ):
            raise ValueError(
                "A newly created service route must form a connected cycle."
            )

"""Baseline scenario plus port and sailing-leg disruptions."""

from config.simulation_config import WARM_UP_DAYS
from maritime_data_context import DisruptionPlan
from .baseline_stable_scenario import BaselineStableScenario


CONGESTED_LEGS = [
    # Format: (departure port, arrival port, start day, duration days, multiplier)
    ("New Jersey", "Cartagena", 120.0, 30.0, 3.0),
    ("Shanghai", "Kaohsiung", 60.0, 20.0, 5.0),
    ("Kaohsiung", "Busan", 60.0, 18.0, 4.0),
    ("Kaohsiung", "Los Angeles", 60.0, 20.0, 5.0),
]


CLOSED_PORTS = [
    # Format: (port, start day, duration days)
    ("Cartagena", 125.0, 14.0),
    ("Kaohsiung", 60.0, 14.0),
]
 

def create_with_disruption(warm_up_days=WARM_UP_DAYS):
    """Create disruptions whose configured start days are measurement-relative."""
    context = BaselineStableScenario.create()

    for congested_leg in CONGESTED_LEGS:
        departure, arrival, start_day, duration, multiplier = congested_leg
        _add_congested_leg(
            context,
            departure,
            arrival,
            warm_up_days + start_day,
            duration,
            multiplier,
        )

    for closed_port in CLOSED_PORTS:
        port, start_day, duration = closed_port
        _add_closed_port(
            context,
            port,
            warm_up_days + start_day,
            duration,
        )

    return context


def _add_congested_leg(
    context,
    departure_port_name,
    arrival_port_name,
    start_offset_days,
    duration_days,
    multiplier,
):
    _validate_timing(start_offset_days, duration_days)
    if multiplier <= 1.0:
        raise ValueError("A congested-leg multiplier must be greater than 1.0.")

    legs = _require_legs(context, departure_port_name, arrival_port_name)

    for leg in legs:
        context.disruption_plans.append(
            DisruptionPlan(
                target_leg=leg,
                start_offset_days=start_offset_days,
                duration_days=duration_days,
                multiplier=multiplier,
            )
        )


def _add_closed_port(
    context,
    port_name,
    start_offset_days,
    duration_days,
):
    _validate_timing(start_offset_days, duration_days)
    port = _require_port(context, port_name)
    if not port.berths:
        raise ValueError(
            f"Port '{port.name}' does not have any berths to close."
        )

    for berth in port.berths:
        context.disruption_plans.append(
            DisruptionPlan(
                target_berth=berth,
                start_offset_days=start_offset_days,
                duration_days=duration_days,
                close_berth=True,
            )
        )


def _validate_timing(start_offset_days, duration_days):
    if start_offset_days < 0:
        raise ValueError("start_offset_days must be non-negative.")
    if duration_days <= 0:
        raise ValueError("duration_days must be positive.")


def _find_legs(context, departure_port_name, arrival_port_name):
    departure = departure_port_name.casefold()
    arrival = arrival_port_name.casefold()
    return [
        leg
        for leg in context.legs
        if leg.departure_port.name.casefold() == departure
        and leg.arrival_port.name.casefold() == arrival
    ]


def _require_legs(context, departure_port_name, arrival_port_name):
    legs = _find_legs(context, departure_port_name, arrival_port_name)
    if not legs:
        raise ValueError(
            f"Leg '{departure_port_name}' -> '{arrival_port_name}' "
            "was not found in the baseline scenario."
        )
    return legs


def _find_port(context, port_name):
    name = port_name.casefold()
    return next(
        (port for port in context.ports if port.name.casefold() == name),
        None,
    )


def _require_port(context, port_name):
    port = _find_port(context, port_name)
    if port is None:
        raise ValueError(f"Port '{port_name}' was not found in the baseline scenario.")
    return port

"""Write simulation statistics in the CSV format consumed by the dashboard."""

import csv
import math
from pathlib import Path


def write_all(sim, output_directory) -> None:
    output_directory = _ensure_directory(output_directory)
    _write_demand_matrix(
        output_directory / "Average_Origin_Waiting_TEU_By_OD.csv",
        sim.shipment_waiting_for_loading_at_origin_port.hc_teus_by_demand,
        lambda counter: counter.average_count,
    )
    _write_port_level_statistics(sim, output_directory)
    _write_demand_matrix(
        output_directory / "Average_In_Transit_TEU_By_OD.csv",
        sim.shipment_being_transported.hc_teus_in_transition_by_demand,
        lambda counter: counter.average_count,
    )
    _write_demand_matrix(
        output_directory / "Cumulative_Completed_TEU_By_OD.csv",
        sim.shipment_being_transported.hc_teus_in_transition_by_demand,
        lambda counter: counter.total_decrement,
    )
    _write_service_route_statistics(sim, output_directory)
    _write_vessel_statistics(sim, output_directory)


def write_att_by_period(output_directory, periods) -> None:
    """Write TEU-weighted average shipment transport time by period."""
    output_directory = _ensure_directory(output_directory)
    rows = [["PeriodIndex", "StartDay", "EndDay", "AverageTransportTime"]]
    period_values = []
    for period_index, (start_day, end_day, average_cycle_time) in enumerate(
        sorted(periods, key=lambda item: item[0]),
        start=1,
    ):
        period_values.append(average_cycle_time)
        rows.append(
            [
                period_index,
                start_day,
                end_day,
                f"{average_cycle_time:.2f}",
            ]
        )

    if period_values:
        overall_mean = sum(period_values) / len(period_values)
        variance = (
            sum((value - overall_mean) ** 2 for value in period_values)
            / (len(period_values) - 1)
            if len(period_values) > 1
            else 0.0
        )
        rows.append(["", "", "OverallMean", f"{overall_mean:.2f}"])
        rows.append(["", "", "PeriodStdDev", f"{math.sqrt(variance):.2f}"])

    _write_csv(output_directory / "ATT_By_Statistics_Interval.csv", rows)


def _write_demand_matrix(path, counters, value_selector) -> None:
    origins = sorted({demand.origin_port for demand in counters}, key=lambda port: port.name)
    destinations = sorted(
        {demand.destination_port for demand in counters}, key=lambda port: port.name
    )
    rows = [["Origin \\ Destination", *[port.name for port in destinations]]]
    lookup = {
        (demand.origin_port, demand.destination_port): counter
        for demand, counter in counters.items()
    }
    for origin in origins:
        row = [origin.name]
        for destination in destinations:
            counter = lookup.get((origin, destination))
            row.append("-" if counter is None else _format_integer(value_selector(counter)))
        rows.append(row)
    _write_csv(path, rows)


def _write_port_level_statistics(sim, output_directory) -> None:
    origin = sim.shipment_waiting_for_loading_at_origin_port.hc_teus_by_origin_port
    transshipment = sim.shipment_waiting_for_loading_at_transshipment_port.hc_teus_by_transshipment_port
    vessels = sim.vessel_queuing_for_berth.hc_number_of_vessels_by_port
    ports = sorted(set(origin) | set(transshipment) | set(vessels), key=lambda port: port.name)
    rows = [[
        "Port", "Origin Waiting TEU", "Transshipment Waiting TEU",
        "Total Waiting TEU", "Vessels Waiting",
    ]]
    for port in ports:
        origin_average = _average_count(origin, port)
        transshipment_average = _average_count(transshipment, port)
        rows.append([
            port.name,
            _format_integer(origin_average),
            _format_integer(transshipment_average),
            _format_integer(origin_average + transshipment_average),
            _format_decimal(_average_count(vessels, port)),
        ])
    total_origin = sum(counter.average_count for counter in origin.values())
    total_transshipment = sum(counter.average_count for counter in transshipment.values())
    rows.append([
        "TOTAL",
        _format_integer(total_origin),
        _format_integer(total_transshipment),
        _format_integer(total_origin + total_transshipment),
        _format_decimal(sum(counter.average_count for counter in vessels.values())),
    ])
    _write_csv(
        output_directory / "Port_Waiting_Statistics.csv",
        rows,
    )


def _write_service_route_statistics(sim, output_directory) -> None:
    capacity = sim.vessel_sailing.hc_teu_capacity_by_service_route
    carried = sim.vessel_sailing.hc_carried_teus_by_service_route
    routes = sorted(set(capacity) | set(carried), key=lambda route: route.id)
    rows = [["Route", "Name", "Avg Capacity TEU", "Avg Carried TEU", "Utilization"]]
    for route in routes:
        average_capacity = _average_count(capacity, route)
        average_carried = _average_count(carried, route)
        rows.append([
            route.id,
            route.name,
            _format_integer(average_capacity),
            _format_integer(average_carried),
            _format_percent(average_carried / average_capacity if average_capacity else 0),
        ])
    total_capacity = sum(counter.average_count for counter in capacity.values())
    total_carried = sum(counter.average_count for counter in carried.values())
    rows.append([
        "TOTAL", "", _format_integer(total_capacity), _format_integer(total_carried),
        _format_percent(total_carried / total_capacity if total_capacity else 0),
    ])
    _write_csv(
        output_directory / "Service_Route_Utilization.csv",
        rows,
    )


def _write_vessel_statistics(sim, output_directory) -> None:
    sailing = sim.vessel_sailing.s_hour_counter.average_count
    waiting = sim.vessel_queuing_for_berth.d_hour_counter.average_count
    served = sim.vessel_being_served.d_hour_counter.average_count
    _write_csv(output_directory / "Average_Vessel_State_Counts.csv", [
        ["Metric", "Average Count"],
        ["Average vessels sailing", _format_decimal(sailing)],
        ["Average vessels waiting for berth at port", _format_decimal(waiting)],
        ["Average vessels being served at berth", _format_decimal(served)],
        ["TOTAL average active/port vessels", _format_decimal(sailing + waiting + served)],
    ])


def _average_count(counters, key) -> float:
    counter = counters.get(key)
    return counter.average_count if counter is not None else 0.0


def _format_integer(value) -> str:
    return f"{value:,.0f}"


def _format_decimal(value) -> str:
    return f"{value:,.2f}"


def _format_number(value) -> str:
    return f"{value:.2f}"


def _format_percent(value) -> str:
    return f"{value * 100:.2f}%"


def _ensure_directory(output_directory) -> Path:
    path = Path(output_directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path, rows) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as output:
        csv.writer(output, lineterminator="\n").writerows(rows)

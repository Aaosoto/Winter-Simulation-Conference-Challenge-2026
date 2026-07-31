"""create the stable baseline scenario from editable CSV input tables."""

import csv
from pathlib import Path

from maritime_data_context import (
    Berth,
    Demand,
    Leg,
    MaritimeDataContext,
    Port,
    Segment,
    ServiceRoute,
    Vessel,
    VesselClass,
)


class BaselineStableScenario:
    REQUIRED_INPUT_FILES = (
        "ports.csv",
        "service_routes.csv",
        "route_segments.csv",
        "demand_matrix.csv",
        "vessel_classes.csv",
        "route_plan.csv",
    )

    @staticmethod
    def create(input_directory=None):
        directory = (
            Path(input_directory)
            if input_directory is not None
            else BaselineStableScenario.resolve_default_input_directory()
        )
        return BaselineStableScenario.load_from_directory(directory)

    @staticmethod
    def load_from_directory(input_directory):
        directory = Path(input_directory)
        if not _contains_required_input_files(directory):
            raise FileNotFoundError(f"Baseline input CSVs not found in: {directory}")

        context = MaritimeDataContext()
        ports = _load_ports(context, directory / "ports.csv")
        routes = _load_service_routes(context, directory / "service_routes.csv")
        _load_route_segments(context, ports, routes, directory / "route_segments.csv")
        _load_demands(context, ports, directory / "demand_matrix.csv")
        vessel_classes = _load_vessel_classes(context, directory / "vessel_classes.csv")
        _load_route_plan(context, routes, vessel_classes, directory / "route_plan.csv")
        context.initial_service_routes.extend(context.service_routes)
        return context

    @staticmethod
    def resolve_default_input_directory():
        project_input_directory = Path(__file__).resolve().parents[1] / "Input"
        for candidate in _baseline_input_candidates(project_input_directory):
            if _contains_required_input_files(candidate):
                return candidate

        for directory in [Path.cwd(), *Path.cwd().parents]:
            for input_directory in (
                directory / "SimulationChallenge2026_Py" / "Input",
                directory / "Input",
            ):
                for candidate in _baseline_input_candidates(input_directory):
                    if _contains_required_input_files(candidate):
                        return candidate
        raise FileNotFoundError("Could not locate the baseline CSV input directory.")


def create(input_directory=None):
    return BaselineStableScenario.create(input_directory)


def _baseline_input_candidates(input_directory):
    yield input_directory / "BaselineStable"
    yield input_directory


def _contains_required_input_files(directory):
    return directory.is_dir() and all(
        (directory / file_name).is_file()
        for file_name in BaselineStableScenario.REQUIRED_INPUT_FILES
    )


def _read_rows(path, expected_headers=None):
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        headers = reader.fieldnames or []
        if expected_headers is not None and headers != expected_headers:
            raise ValueError(f"{path}: expected headers {expected_headers}, got {headers}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: at least one data row is required")
    return headers, rows


def _required(row, column, path):
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"{path}: required value missing for '{column}'")
    return value


def _load_ports(context, path):
    _, rows = _read_rows(path, ["PortName", "BerthCount"])
    ports = {}
    for row in rows:
        name = _required(row, "PortName", path)
        berth_count = int(_required(row, "BerthCount", path))
        if berth_count <= 0 or name.casefold() in ports:
            raise ValueError(f"{path}: invalid or duplicate port '{name}'")
        port = Port(name=name)
        port.berths.extend(Berth(index=index, port=port) for index in range(berth_count))
        ports[name.casefold()] = port
        context.ports.append(port)
    return ports


def _load_service_routes(context, path):
    _, rows = _read_rows(path, ["RouteId", "RouteName", "StartDayOfWeek"])
    routes = {}
    for row in rows:
        route_id = _required(row, "RouteId", path)
        start_day = float(_required(row, "StartDayOfWeek", path))
        if not 0 <= start_day < 7 or route_id.casefold() in routes:
            raise ValueError(f"{path}: invalid or duplicate route '{route_id}'")
        route = ServiceRoute(route_id, _required(row, "RouteName", path), start_day)
        routes[route_id.casefold()] = route
        context.service_routes.append(route)
    return routes


def _load_route_segments(context, ports, routes, path):
    _, rows = _read_rows(
        path, ["RouteId", "Sequence", "FromPort", "ToPort", "SailingDistanceNm"]
    )
    for row in rows:
        route = routes[_required(row, "RouteId", path).casefold()]
        departure = ports[_required(row, "FromPort", path).casefold()]
        arrival = ports[_required(row, "ToPort", path).casefold()]
        sequence = int(_required(row, "Sequence", path))
        distance = float(_required(row, "SailingDistanceNm", path))
        if sequence <= 0 or distance <= 0 or departure is arrival:
            raise ValueError(f"{path}: invalid route segment")
        leg = Leg(departure, arrival, distance)
        segment = Segment(sequence, leg, route)
        context.legs.append(leg)
        context.partial_service_routes.append(segment)
        departure.outgoing_legs.append(leg)
        arrival.incoming_legs.append(leg)
        leg.segments.append(segment)
        route.segments.append(segment)

    for route in routes.values():
        route.segments.sort(key=lambda segment: segment.sequence_index)
        expected = list(range(1, len(route.segments) + 1))
        if [segment.sequence_index for segment in route.segments] != expected:
            raise ValueError(f"{path}: route '{route.id}' has invalid segment sequence")


def _load_demands(context, ports, path):
    headers, rows = _read_rows(path)
    if not headers or headers[0].casefold() not in {"origin\\destination", "origin"}:
        raise ValueError(f"{path}: first column must be 'Origin\\Destination'")
    for row in rows:
        origin = ports[_required(row, headers[0], path).casefold()]
        for destination_name in headers[1:]:
            annual_teus = int(_required(row, destination_name, path))
            if annual_teus <= 0:
                continue
            destination = ports[destination_name.casefold()]
            if origin is destination:
                raise ValueError(f"{path}: positive diagonal demand is not allowed")
            demand = Demand(origin, destination, annual_teus)
            context.demands.append(demand)
            origin.outgoing_demands.append(demand)
            destination.incoming_demands.append(demand)


def _load_vessel_classes(context, path):
    _, rows = _read_rows(
        path, ["VesselClassName", "TeuCapacity", "SailingSpeedKnots", "LOAMeters"]
    )
    vessel_classes = {}
    for row in rows:
        name = _required(row, "VesselClassName", path)
        vessel_class = VesselClass(
            name,
            int(_required(row, "TeuCapacity", path)),
            float(_required(row, "SailingSpeedKnots", path)),
            float(_required(row, "LOAMeters", path)),
        )
        if min(vessel_class.teu_capacity, vessel_class.sailing_speed, vessel_class.loa) <= 0:
            raise ValueError(f"{path}: vessel class attributes must be positive")
        vessel_classes[name.casefold()] = vessel_class
        context.vessel_classes.append(vessel_class)
    return vessel_classes


def _load_route_plan(context, routes, vessel_classes, path):
    _, rows = _read_rows(path, ["RouteId", "VesselClassName", "VesselCount"])
    vessel_index = 1
    for row in rows:
        route = routes[_required(row, "RouteId", path).casefold()]
        vessel_class = vessel_classes[_required(row, "VesselClassName", path).casefold()]
        vessel_count = int(_required(row, "VesselCount", path))
        if vessel_count <= 0:
            raise ValueError(f"{path}: VesselCount must be positive")
        for _ in range(vessel_count):
            vessel = Vessel(vessel_index, vessel_class, route)
            vessel_index += 1
            context.vessels.append(vessel)
            vessel_class.vessels.append(vessel)
            route.deployed_vessels.append(vessel)

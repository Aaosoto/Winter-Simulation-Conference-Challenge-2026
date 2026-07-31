"""
Main entry point for WSC Simulation Challenge 2026 Python simulation.

Equivalent to main entry point - runs the maritime shipping simulation,
prints statistics at the configured statistics interval, and launches the dashboard
server (dashboard/serve_gui.py) so the Output/ CSVs can be inspected
in a browser once the run finishes.
"""

import datetime as dt
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from config.simulation_config import (
    SIMULATION_DAYS,
    STATISTICS_INTERVAL_DAYS,
    WARM_UP_DAYS,
)
import scenario_builders
from simulation_model import Model
from simulation_output_csv_writer import (
    write_all,
    write_att_by_period,
)


# Project root = the directory containing main.py (parent of dashboard/ and Output/).
PROJECT_ROOT = Path(__file__).resolve().parent
DASHBOARD_SCRIPT = PROJECT_ROOT / "dashboard" / "serve_gui.py"
DASHBOARD_URL = "http://127.0.0.1:8000/dashboard/"
OUTPUT_DIRECTORY = PROJECT_ROOT / "Output"
LOGS_DIRECTORY = PROJECT_ROOT / "Logs"


def main():
    LOGS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIRECTORY / (
        f"{dt.datetime.now():%Y%m%d%H%M}_SimulationProgressResults.log"
    )
    original_stdout = sys.stdout

    with log_path.open("w", encoding="utf-8", newline="") as log_output:
        sys.stdout = TeeTextWriter(original_stdout, log_output)
        try:
            run_simulation()
        finally:
            sys.stdout.flush()
            sys.stdout = original_stdout

    print(f"Simulation log written to: {log_path}")
    launch_dashboard()


def run_simulation():
    simulation_run_started_at = time.perf_counter()

    # Choose the scenario by commenting/uncommenting the two lines below.
    context = scenario_builders.create_with_disruption()  # Scenario with a disruption and demand replacement.
    # context = scenario_builders.create()  # Baseline scenario without disruptions.

    # create simulation model with seed=1
    sim = Model(context, seed=2026)

    print(f"Simulation warm-up started: {WARM_UP_DAYS:,} days")
    sim.warmup(period=dt.timedelta(days=WARM_UP_DAYS))
    print(
        "Simulation warm-up completed. "
        f"Measurement starts at simulation day {WARM_UP_DAYS:,}."
    )
    print()

    simulation_days = SIMULATION_DAYS
    statistics_interval_days = STATISTICS_INTERVAL_DAYS
    att_period_rows = []
    period_start_day = 1
    period_start_time = sim.clock_time

    for day in range(1, simulation_days + 1):
        # Advance the simulation one day at a time.
        sim.run(duration=dt.timedelta(days=1))

        period_ends_today = (
            day % statistics_interval_days == 0
            or day == simulation_days
        )
        if not period_ends_today:
            continue

        average_transport_time_days = (
            sim.get_teu_weighted_average_transport_time_hours(
                period_start_time,
                sim.clock_time,
            )
            / 24.0
        )
        att_period_rows.append(
            (period_start_day, day, average_transport_time_days)
        )
        # Print statistics
        clear_console_screen()

        print(f"Simulation Progress: Day {day:,} / {simulation_days:,}")
        print(f"Simulation Clock Time: {sim.clock_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        print_shipment_and_port_statistics(sim)
        print_shipment_being_transported_statistics(sim)
        print_service_route_capacity_utilization_statistics(sim)
        print_vessel_statistics(sim)
        print()
        print(
            f"Period Result Output: Period {len(att_period_rows):,} "
            f"(Days {period_start_day:,}-{day:,})"
        )
        print(f"Output Simulation Day: {day:,}")
        running_seconds = time.perf_counter() - simulation_run_started_at
        print(f"Simulation Running Time: {_format_running_time(running_seconds)}")
        print()

        period_start_day = day + 1
        period_start_time = sim.clock_time

    print("Simulation completed.")
    write_all(sim, OUTPUT_DIRECTORY)
    write_att_by_period(OUTPUT_DIRECTORY, att_period_rows)
    print(f"CSV output written to: {OUTPUT_DIRECTORY}")
    print()


def _format_running_time(total_seconds) -> str:
    """Format elapsed wall-clock time as HH:MM:SS."""
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def launch_dashboard() -> None:
    """Run dashboard/serve_gui.py in the background so Output CSVs are browsable.

    Mirrors the original dashboard launcher helper: the dashboard
    server runs as an independent process rooted at PROJECT_ROOT, so it can
    serve ../Output/<file>.csv on the same origin that dashboard/app.js expects.
    """
    if not DASHBOARD_SCRIPT.is_file():
        print(
            f"Dashboard server script not found at {DASHBOARD_SCRIPT}. "
            "Skipping auto-launch.",
            file=sys.stderr,
        )
        return

    # Keep the script path quoted so a leading "." or spaces survive parsing.
    arguments = [sys.executable, str(DASHBOARD_SCRIPT), "--no-open"]

    # Keep the local server hidden on Windows. On other platforms, start it in
    # an independent session so it remains available after this process exits.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        # Use forward slashes — Python on Windows accepts them and they survive
        # the .py launcher round-trip without escaping headaches.
        arguments[1] = "./dashboard/serve_gui.py"

    try:
        subprocess.Popen(
            arguments,
            cwd=str(PROJECT_ROOT),
            creationflags=creationflags,
            close_fds=True,
            start_new_session=sys.platform != "win32",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Launched dashboard server in the background.")
        print(f"Dashboard URL : {DASHBOARD_URL}")
        if wait_for_dashboard(DASHBOARD_URL):
            open_dashboard_browser(DASHBOARD_URL)
        else:
            print(
                f"Dashboard server did not respond. Open {DASHBOARD_URL} manually "
                "and check whether another process is already using port 8000.",
                file=sys.stderr,
            )
    except OSError as exc:
        # Most common cause: 'python' executable not resolvable.
        print(f"Could not start dashboard server: {exc}", file=sys.stderr)
        print(
            f"To launch it manually: cd \"{PROJECT_ROOT}\" && "
            f"{sys.executable} {DASHBOARD_SCRIPT}",
            file=sys.stderr,
        )


def wait_for_dashboard(url: str, timeout_seconds: float = 10.0) -> bool:
    """Wait until the dashboard server responds or the timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    return False


def open_dashboard_browser(url: str) -> None:
    """Open the dashboard using the most reliable method for this platform."""
    try:
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
        elif not webbrowser.open(url, new=2):
            raise OSError("No browser accepted the URL")
        print(f"Opened dashboard in the default browser: {url}")
    except OSError as exc:
        print(f"Could not open the browser automatically: {exc}", file=sys.stderr)
        print(f"Open this URL manually: {url}", file=sys.stderr)


def clear_console_screen():
    """Clear console screen (no-op if output redirected)."""
    pass  # Simplified for Python


class TeeTextWriter:
    """Write identical text to the console and a simulation log file."""

    def __init__(self, console_writer, file_writer):
        self.console_writer = console_writer
        self.file_writer = file_writer

    def write(self, value):
        self.console_writer.write(value)
        self.file_writer.write(value)
        return len(value)

    def flush(self):
        self.console_writer.flush()
        self.file_writer.flush()


def print_shipment_and_port_statistics(sim: Model) -> None:
    """Print shipment waiting and port-level statistics."""
    origin_activity = sim.shipment_waiting_for_loading_at_origin_port
    transshipment_activity = sim.shipment_waiting_for_loading_at_transshipment_port
    vessel_queue_activity = sim.vessel_queuing_for_berth

    print()
    print("============================================================")
    print("Shipment Waiting for Loading Statistics")
    print("============================================================")

    print_teus_by_demand_matrix(origin_activity)
    print_port_level_statistics(origin_activity, transshipment_activity, vessel_queue_activity)

    print()


def print_shipment_being_transported_statistics(sim: Model) -> None:
    """Print shipment in-transit statistics."""
    activity = sim.shipment_being_transported

    print()
    print("============================================================")
    print("Shipment Being Transported Statistics")
    print("============================================================")

    print_average_teus_in_transition_by_demand_matrix(activity)
    print_completed_teus_by_demand_matrix(activity)

    print()


def print_teus_by_demand_matrix(activity) -> None:
    """Print TEUs by demand matrix (origin-destination grid)."""
    print()
    print("TEUs by Demand Matrix")
    print("------------------------------------------------------------")

    # Get unique origins and destinations
    demands = list(activity.hc_teus_by_demand.keys())
    origins = sorted(set(d.origin_port for d in demands), key=lambda p: p.name)
    destinations = sorted(set(d.destination_port for d in demands), key=lambda p: p.name)

    first_col = 18
    cell = 14

    # Header row
    print(f"{'Origin Dest':<{first_col}}", end="")
    for dest in destinations:
        print(f"{dest.name:<{cell}}", end="")
    print()

    # Separator
    print("-" * (first_col + cell * len(destinations)))

    # Data rows
    for origin in origins:
        print(f"{origin.name:<{first_col}}", end="")
        for dest in destinations:
            counter = None
            for d, c in activity.hc_teus_by_demand.items():
                if d.origin_port == origin and d.destination_port == dest:
                    counter = c
                    break

            if counter is None:
                print(f"{'-':<{cell}}", end="")
            else:
                print(f"{counter.average_count:<{cell}.0f}", end="")
        print()


def print_port_level_statistics(origin_activity, transshipment_activity, vessel_queue_activity) -> None:
    """Print port-level shipment waiting and vessel queue statistics."""
    print()
    print("Port-Level Shipment Waiting and Vessel Queue Statistics")
    print()

    # Header
    print(f"{'Port':<25}" +
          f"{'Origin Waiting TEU':>20}" +
          f"{'Transshipment Waiting TEU':>28}" +
          f"{'Total Waiting TEU':>20}" +
          f"{'Vessels Waiting':>18}")
    print("-" * 111)

    # Get all ports
    all_ports = set(origin_activity.hc_teus_by_origin_port.keys())
    all_ports.update(transshipment_activity.hc_teus_by_transshipment_port.keys())
    all_ports.update(vessel_queue_activity.hc_number_of_vessels_by_port.keys())
    sorted_ports = sorted(all_ports, key=lambda p: p.name)

    total_origin = 0.0
    total_trans = 0.0
    total_vessels = 0.0

    for port in sorted_ports:
        origin_teu = origin_activity.hc_teus_by_origin_port.get(port)
        origin_avg = origin_teu.average_count if origin_teu else 0.0

        trans_teu = transshipment_activity.hc_teus_by_transshipment_port.get(port)
        trans_avg = trans_teu.average_count if trans_teu else 0.0

        vessels = vessel_queue_activity.hc_number_of_vessels_by_port.get(port)
        vessels_avg = vessels.average_count if vessels else 0.0

        total_origin += origin_avg
        total_trans += trans_avg
        total_vessels += vessels_avg

        print(f"{port.name:<25}" +
              f"{origin_avg:>20,.0f}" +
              f"{trans_avg:>28,.0f}" +
              f"{origin_avg + trans_avg:>20,.0f}" +
              f"{vessels_avg:>18,.2f}")

    print("-" * 111)
    print(f"{'TOTAL':<25}" +
          f"{total_origin:>20,.0f}" +
          f"{total_trans:>28,.0f}" +
          f"{total_origin + total_trans:>20,.0f}" +
          f"{total_vessels:>18,.2f}")

    print()


def print_average_teus_in_transition_by_demand_matrix(activity) -> None:
    """Print average TEUs in transition by demand matrix."""
    print()
    print("Average TEUs in Transition by Demand Matrix")
    print("------------------------------------------------------------")

    print_demand_matrix(
        activity.hc_teus_in_transition_by_demand,
        lambda c: c.average_count,
        "N0"
    )


def print_completed_teus_by_demand_matrix(activity) -> None:
    """Print completed TEUs by demand matrix."""
    print()
    print("Completed TEUs by Demand Matrix")
    print("------------------------------------------------------------")

    print_demand_matrix(
        activity.hc_teus_in_transition_by_demand,
        lambda c: c.total_decrement,
        "N0"
    )


def print_demand_matrix(counters, value_selector, number_format) -> None:
    """Print a demand matrix with given counter value selector."""
    demands = list(counters.keys())
    origins = sorted(set(d.origin_port for d in demands), key=lambda p: p.name)
    destinations = sorted(set(d.destination_port for d in demands), key=lambda p: p.name)

    first_col = 18
    cell = 14

    # Header row
    print(f"{'Origin Dest':<{first_col}}", end="")
    for dest in destinations:
        print(f"{dest.name:<{cell}}", end="")
    print()

    # Separator
    print("-" * (first_col + cell * len(destinations)))

    # Data rows
    for origin in origins:
        print(f"{origin.name:<{first_col}}", end="")
        for dest in destinations:
            counter = None
            for d, c in counters.items():
                if d.origin_port == origin and d.destination_port == dest:
                    counter = c
                    break

            if counter is None:
                print(f"{'-':<{cell}}", end="")
            else:
                value = value_selector(counter)
                print(f"{value:<{cell}.0f}", end="")
        print()


def print_vessel_statistics(sim: Model) -> None:
    """Print vessel activity statistics."""
    print()
    print("============================================================")
    print("Vessel Statistics")
    print("============================================================")

    # Get hour counters from activities
    vessel_sailing = sim.vessel_sailing
    vessel_queuing = sim.vessel_queuing_for_berth
    vessel_being_served = sim.vessel_being_served

    # Get average counts from hour counters
    # Reference: sim.vessel_sailing.s_hour_counter.AverageCount
    # Reference: sim.vessel_queuing_for_berth.d_hour_counter.AverageCount
    # Reference: sim.vessel_being_served.d_hour_counter.AverageCount
    avg_sailing = vessel_sailing.s_hour_counter.average_count
    avg_queuing = vessel_queuing.d_hour_counter.average_count
    avg_being_served = vessel_being_served.d_hour_counter.average_count

    print(f"{'Metric':<45}{'Average Count':>18}")
    print("-" * 63)
    print(f"{'Average vessels sailing':<45}{avg_sailing:>18,.2f}")
    print(f"{'Average vessels waiting for berth at port':<45}{avg_queuing:>18,.2f}")
    print(f"{'Average vessels being served at berth':<45}{avg_being_served:>18,.2f}")
    print("-" * 63)
    print(f"{'TOTAL average active/port vessels':<45}{avg_sailing + avg_queuing + avg_being_served:>18,.2f}")

    print()


def print_service_route_capacity_utilization_statistics(sim: Model) -> None:
    """Print service route capacity and utilization statistics."""
    vessel_sailing_activity = sim.vessel_sailing

    print()
    print("============================================================")
    print("Service Route Capacity and Utilization Statistics")
    print("============================================================")

    print(f"{'Route':<10}" +
          f"{'Name':<32}" +
          f"{'Avg Capacity TEU':>20}" +
          f"{'Avg Carried TEU':>20}" +
          f"{'Utilization':>15}")
    print("-" * 97)

    # Get all service routes
    all_routes = set(vessel_sailing_activity.hc_teu_capacity_by_service_route.keys())
    all_routes.update(vessel_sailing_activity.hc_carried_teus_by_service_route.keys())
    sorted_routes = sorted(all_routes, key=lambda r: r.id)

    for route in sorted_routes:
        capacity_counter = vessel_sailing_activity.hc_teu_capacity_by_service_route.get(route)
        carried_counter = vessel_sailing_activity.hc_carried_teus_by_service_route.get(route)

        avg_capacity = capacity_counter.average_count if capacity_counter else 0.0
        avg_carried = carried_counter.average_count if carried_counter else 0.0

        utilization = (avg_carried / avg_capacity * 100) if avg_capacity > 0 else 0.0

        print(f"{route.id:<10}" +
              f"{route.name:<32}" +
              f"{avg_capacity:>20,.0f}" +
              f"{avg_carried:>20,.0f}" +
              f"{utilization:>14.2f}%")

    # TOTAL row for all vessel states.
    print("-" * 97)

    total_capacity = sum(
        c.average_count for c in vessel_sailing_activity.hc_teu_capacity_by_service_route.values()
    )
    total_carried = sum(
        c.average_count for c in vessel_sailing_activity.hc_carried_teus_by_service_route.values()
    )
    total_util = (total_carried / total_capacity * 100) if total_capacity > 0 else 0.0

    print(f"{'TOTAL':<10}" +
          f"{'':<32}" +
          f"{total_capacity:>20,.0f}" +
          f"{total_carried:>20,.0f}" +
          f"{total_util:>14.2f}%")

    print()


if __name__ == "__main__":
    main()

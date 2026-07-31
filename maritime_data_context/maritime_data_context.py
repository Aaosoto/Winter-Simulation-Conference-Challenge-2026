"""In-memory maritime data container and baseline compatibility entry point."""

from typing import List

from .demand import Demand
from .disruption_plan import DisruptionPlan
from .leg import Leg
from .port import Port
from .segment import Segment
from .service_route import ServiceRoute
from .vessel import Vessel
from .vessel_class import VesselClass


class MaritimeDataContext:
    """Stores the maritime domain data used by a simulation scenario."""

    def __init__(self):
        self.ports: List[Port] = []
        self.demands: List[Demand] = []
        self.service_routes: List[ServiceRoute] = []
        self.initial_service_routes: List[ServiceRoute] = []
        self.legs: List[Leg] = []
        self.partial_service_routes: List[Segment] = []
        self.vessel_classes: List[VesselClass] = []
        self.vessels: List[Vessel] = []
        self.disruption_plans: List[DisruptionPlan] = []


class MaritimeDataInitializer:
    """Compatibility wrapper for the CSV-backed stable baseline scenario."""

    @staticmethod
    def create() -> MaritimeDataContext:
        """create the same baseline context as ``BaselineStableScenario.create``."""
        # Import lazily to avoid a package import cycle:
        # scenario_builders imports MaritimeDataContext domain classes.
        from scenario_builders.baseline_stable_scenario import BaselineStableScenario

        return BaselineStableScenario.create()

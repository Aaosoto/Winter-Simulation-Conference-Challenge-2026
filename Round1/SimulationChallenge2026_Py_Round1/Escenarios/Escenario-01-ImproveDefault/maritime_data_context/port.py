"""
Represents a port in the maritime network.

A port has berths for vessel loading/unloading operations,
outgoing and incoming sailing legs, and associated demands.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .berth import Berth
    from .leg import Leg
    from .demand import Demand
    from .shipment import Shipment


class Port:
    def __init__(self, name: str = ""):
        self.name = name
        self.berths: List['Berth'] = []
        self.outgoing_legs: List['Leg'] = []
        self.incoming_legs: List['Leg'] = []
        self.outgoing_demands: List['Demand'] = []
        self.incoming_demands: List['Demand'] = []
        self.shipments_in_storage: List['Shipment'] = []

    def __repr__(self):
        return self.name
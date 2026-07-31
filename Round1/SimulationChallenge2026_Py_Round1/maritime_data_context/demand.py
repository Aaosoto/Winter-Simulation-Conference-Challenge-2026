"""
Represents an origin-destination container demand between two ports.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .port import Port
    from .shipment import Shipment


class Demand:
    def __init__(
        self,
        origin_port: 'Port' = None,
        destination_port: 'Port' = None,
        annual_teus: int = 0
    ):
        self.origin_port = origin_port
        self.destination_port = destination_port
        self.annual_teus = annual_teus
        self.shipments: List['Shipment'] = []

    def __repr__(self):
        return f"{self.origin_port.name} -> {self.destination_port.name}: {self.annual_teus}"
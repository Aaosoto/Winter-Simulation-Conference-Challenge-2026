"""
Represents a physical sailing leg between two ports.

A leg defines the geographical connection from a departure port
to an arrival port, together with the sailing distance between them.

In the routing structure, one leg may be associated with one or
more service-route segments. This is useful when the same physical
port-to-port connection is reused by different service routes.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .port import Port
    from .segment import Segment


class Leg:
    def __init__(
        self,
        departure_port: 'Port' = None,
        arrival_port: 'Port' = None,
        sailing_distance: float = 0.0
    ):
        self.departure_port = departure_port
        self.arrival_port = arrival_port
        self.sailing_distance = sailing_distance
        self.segments: List['Segment'] = []
        self.sailing_time_multiplier = 1.0

    def __repr__(self):
        return f"{self.departure_port} -> {self.arrival_port} ({self.sailing_distance} nm)"

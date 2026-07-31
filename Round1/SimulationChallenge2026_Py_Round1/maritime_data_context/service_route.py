"""
Represents a cyclic liner shipping service route.

A service route defines an ordered sequence of route segments. Each
segment refers to a physical port-to-port leg, while the sequence of
segments defines the operational rotation followed by deployed vessels.

Bookings associated with this route specify how shipments use this
service route, including their departure and arrival segment indices.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .segment import Segment
    from .vessel import Vessel
    from .booking import Booking


class ServiceRoute:
    def __init__(
        self,
        id: str = "",
        name: str = "",
        start_day_of_week: float = 0.0
    ):
        self.id = id
        self.name = name
        self.start_day_of_week = start_day_of_week
        self.segments: List['Segment'] = []
        self.deployed_vessels: List['Vessel'] = []
        self.associated_bookings: List['Booking'] = []
        self.source_service_route: 'ServiceRoute' = None
        self.disruption_key = None

    def __repr__(self):
        return f"{self.id} | StartDay={self.start_day_of_week:.2f}"

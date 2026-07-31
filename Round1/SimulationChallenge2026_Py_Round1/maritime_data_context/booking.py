"""
Represents a booking linking a shipment to a service route segment.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .shipment import Shipment
    from .service_route import ServiceRoute


class Booking:
    def __init__(
        self,
        sequence_index: int = 0,
        shipment: 'Shipment' = None,
        service_route: 'ServiceRoute' = None,
        departure_segment_index: int = 0,
        arrival_segment_index: int = 0
    ):
        self.sequence_index = sequence_index
        self.shipment = shipment
        self.service_route = service_route
        self.departure_segment_index = departure_segment_index
        self.arrival_segment_index = arrival_segment_index

    def __repr__(self):
        return (f"Booking-{self.sequence_index} ({self.service_route.id}: "
                f"Seg{self.departure_segment_index}->Seg{self.arrival_segment_index})")
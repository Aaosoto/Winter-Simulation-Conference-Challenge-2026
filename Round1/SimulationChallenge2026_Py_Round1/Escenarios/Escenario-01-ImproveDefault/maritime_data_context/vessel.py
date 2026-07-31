"""
Represents an individual vessel deployed on a service route.

A vessel has an index, a vessel class defining its capacity/speed,
and an assigned service route. It tracks its current position in the
route and the shipments it carries.
"""

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .vessel_class import VesselClass
    from .service_route import ServiceRoute
    from .segment import Segment
    from .berth import Berth
    from .shipment import Shipment


class Vessel:
    def __init__(
        self,
        index: int = 0,
        vessel_class: 'VesselClass' = None,
        assigned_service_route: 'ServiceRoute' = None
    ):
        self.index = index
        self.vessel_class = vessel_class
        self.assigned_service_route = assigned_service_route
        self.pending_assigned_service_route: Optional['ServiceRoute'] = None
        self.current_segment: Optional['Segment'] = None
        self.current_berth: Optional['Berth'] = None
        self.carried_shipments: List['Shipment'] = []

    def get_next_segment(self) -> 'Segment':
        """
        Gets the next segment in the cyclic service route.

        Reference behavior:
          - Get first segment by ordered SequenceIndex
          - If CurrentSegment is null, return first segment
          - Else find next segment with SequenceIndex > CurrentSegment.sequence_index
          - If none found (end of route), wrap around to first segment
        """
        if self.assigned_service_route is None:
            raise ValueError(f"Vessel {self.index} has no assigned service route")

        segments = sorted(self.assigned_service_route.segments, key=lambda s: s.sequence_index)
        if not segments:
            raise ValueError(f"Service route {self.assigned_service_route.id} has no segments")

        first_segment = segments[0]

        if self.current_segment is None:
            return first_segment

        # Find next segment with SequenceIndex > CurrentSegment.sequence_index
        for s in segments:
            if s.sequence_index > self.current_segment.sequence_index:
                return s

        # Wrap around to first segment
        return first_segment

    def _get_shipments_at_segment(self, segment, segment_index_selector):
        """
        Reference helper GetShipmentsAtSegment(Segment segment, Func<Booking, int> segmentIndexSelector).

        Raises ValueError if AssignedServiceRoute is None.
        Raises ValueError if segment is None.
        Returns carried shipments whose current booking:
          1. Belongs to the vessel's assigned service route
          2. Has the matching segment index (departure for loading, arrival for discharging)
        """
        if self.assigned_service_route is None:
            raise ValueError(
                f"Vessel {self.index} has no assigned service route."
            )
        if segment is None:
            raise ValueError(
                f"Vessel {self.index} got null segment in _get_shipments_at_segment."
            )

        result = []
        for shipment in self.carried_shipments:
            booking = shipment.get_current_booking()
            # get_current_booking now raises if no booking matches, so booking is always valid here
            if booking.service_route == self.assigned_service_route and segment_index_selector(booking) == segment.sequence_index:
                result.append(shipment)
        return result

    def get_loading_shipments_at_next_segment(self) -> List['Shipment']:
        """
        Reference behavior:
          var nextSegment = get_next_segment();
          return GetShipmentsAtSegment(nextSegment, booking => booking.departure_segment_index);
        """
        next_segment = self.get_next_segment()
        return self._get_shipments_at_segment(next_segment, lambda b: b.departure_segment_index)

    def get_discharging_shipments_at_current_segment(self) -> List['Shipment']:
        """
        Reference behavior:
          if (CurrentSegment == null) return new HashSet<Shipment>();
          return GetShipmentsAtSegment(CurrentSegment, booking => booking.arrival_segment_index);
        """
        if self.current_segment is None:
            return []
        return self._get_shipments_at_segment(self.current_segment, lambda b: b.arrival_segment_index)

    def __repr__(self):
        return f"Vessel-{self.index} ({self.vessel_class.name if self.vessel_class else 'N/A'})"

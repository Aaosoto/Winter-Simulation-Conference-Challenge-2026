"""
Represents an ordered segment within a liner service route.

A segment is the service-route-level use of a physical leg. While a
Leg describes the physical movement from one port to another,
a segment describes where that movement appears in a specific service route
sequence.

This distinction is useful because the same physical leg may be reused by
different service routes, while each segment belongs to exactly one service
route and has its own sequence index within that route.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .leg import Leg
    from .service_route import ServiceRoute
    from .vessel import Vessel


class Segment:
    def __init__(
        self,
        sequence_index: int = 0,
        associated_leg: 'Leg' = None,
        associated_service_route: 'ServiceRoute' = None
    ):
        self.sequence_index = sequence_index
        self.associated_leg = associated_leg
        self.associated_service_route = associated_service_route
        self.current_vessels: List['Vessel'] = []

    def __repr__(self):
        return f"{self.associated_service_route.id}-{self.sequence_index}"
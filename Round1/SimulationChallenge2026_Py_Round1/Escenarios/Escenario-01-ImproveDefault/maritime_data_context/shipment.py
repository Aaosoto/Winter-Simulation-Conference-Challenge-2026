"""
Represents a container shipment to be transported through the network.
"""

import datetime as dt
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .demand import Demand
    from .booking import Booking
    from .vessel import Vessel
    from .port import Port


class Shipment:
    def __init__(
        self,
        index: int = 0,
        teu_size: int = 0,
        demand: 'Demand' = None,
        current_storage_port: 'Port' = None,
        generated_time: Optional[dt.datetime] = None,
    ):
        self.index = index
        self.teu_size = teu_size
        self.demand = demand
        self.current_storage_port = current_storage_port
        self.generated_time = generated_time
        self.completion_time: Optional[dt.datetime] = None
        self.associated_bookings: List['Booking'] = []
        self.current_booking_index: Optional[int] = None
        self.carrying_vessel: Optional['Vessel'] = None

    def get_current_booking(self) -> 'Booking':
        """Gets the current booking based on CurrentBookingIndex.

        Raises ValueError if no booking matches CurrentBookingIndex.
        Matches Reference Shipment.get_current_booking() which raises InvalidOperationException.
        """
        if self.current_booking_index is None:
            raise ValueError(
                f"Shipment {self.index} has no CurrentBookingIndex set."
            )
        for booking in self.associated_bookings:
            if booking.sequence_index == self.current_booking_index:
                return booking
        raise ValueError(
            f"Shipment {self.index} has no booking matching "
            f"CurrentBookingIndex {self.current_booking_index}."
        )

    def is_at_last_booking(self) -> bool:
        """Returns True if the shipment is at its last booking.

        Matches Reference Shipment.is_at_last_booking():
          var currentBooking = get_current_booking();  // raises if invalid
          var lastSequenceIndex = AssociatedBookings.Max(b => b.sequence_index);
          return currentBooking.sequence_index == lastSequenceIndex;
        """
        current_booking = self.get_current_booking()
        last_sequence_index = max(b.sequence_index for b in self.associated_bookings)
        return current_booking.sequence_index == last_sequence_index

    def __repr__(self):
        return f"Shipment-{self.index} ({self.teu_size} TEU)"

"""
Shipment Waiting For Loading At Transshipment Port Activity.

Reference behavior: ActivityHandler<Shipment> with:
  - No external start/finish gates (base class handles R→S/D→F)
  - attempt_finish: advance CurrentBookingIndex to next booking, then finish(shipment)
  - hc_teus_by_transshipment_port statistics
  - on_finish → ConnectTo wires to ShipmentBeingTransported

State flow (base class 4-state machine R→S→D→F):
  signal_start(shipment) → R → Schedule(attempt_start)
  attempt_start → base.start(shipment) → S (auto-schedules ready_finish)
  ready_finish → D (scheduled by base class start)
  attempt_finish → advance booking index → base.finish(shipment) → F, on_finish fires
"""

from typing import TYPE_CHECKING, Dict

from o2des.common import ActionSet
from o2des.core import HourCounter
from .activity_handler import ActivityHandler

if TYPE_CHECKING:
    from maritime_data_context import MaritimeDataContext, Port, Shipment


class ShipmentWaitingForLoadingAtTransshipmentPort(ActivityHandler):
    """
    Represents shipments waiting for loading at a transshipment port.

    Before finishing, advances CurrentBookingIndex to the next booking
    in the shipment's booking chain.
    """

    def __init__(self, data_context: 'MaritimeDataContext' = None, seed: int = 0):
        super().__init__(seed=seed, id="ShipmentWaitingForLoadingAtTransshipmentPort")
        self.maritime_data_context = data_context

        # Statistics — pre-create per-port HourCounters so that
        # _creation_time = sim start (= 0), matching the reference behavior's AddHourCounter().
        # Without eager creation, the first transshipment arriving at a
        # port would create the counter late, biasing the per-port TEU avg.
        self._hc_teus_by_transshipment_port: Dict['Port', HourCounter] = {}
        if data_context is not None:
            for port in data_context.ports:
                self._hc_teus_by_transshipment_port[port] = self.add_hour_counter()

        self._on_finish = ActionSet(object)

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def hc_teus_by_transshipment_port(self) -> Dict['Port', HourCounter]:
        return self._hc_teus_by_transshipment_port

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    # -------------------------------------------------------------------------
    # Override attempt_finish — advance booking index
    # -------------------------------------------------------------------------

    def attempt_finish(self) -> None:
        """
        Reference attempt_finish:
          foreach shipment in d_loads_ready_finish:
            currentBooking = AssociatedBookings[CurrentBookingIndex]
            Advance to next booking in chain
            finish(shipment)
        """
        for shipment in list(self.d_loads_ready_finish):
            current_booking_index = shipment.current_booking_index

            # Find current booking
            current_booking = None
            for b in shipment.associated_bookings:
                if b.sequence_index == current_booking_index:
                    current_booking = b
                    break

            if current_booking is None:
                continue

            # Advance to next booking
            next_booking = None
            for b in shipment.associated_bookings:
                if b.sequence_index > current_booking_index:
                    if next_booking is None or b.sequence_index < next_booking.sequence_index:
                        next_booking = b

            if next_booking is None:
                continue

            shipment.current_booking_index = next_booking.sequence_index

            # finish this waiting activity (D → F)
            self.finish(shipment)

    # -------------------------------------------------------------------------
    # Statistics — TEU by Transshipment Port
    # -------------------------------------------------------------------------

    def start(self, shipment: 'Shipment') -> None:
        """Record TEU statistics when shipment enters this activity."""
        super().start(shipment)

        transshipment_port = self._get_arrival_transshipment_port(shipment)
        if transshipment_port not in self._hc_teus_by_transshipment_port:
            self._hc_teus_by_transshipment_port[transshipment_port] = self.add_hour_counter()
        self._hc_teus_by_transshipment_port[transshipment_port].observe_change(shipment.teu_size)

    def depart(self, shipment: 'Shipment') -> None:
        """Remove TEU statistics when shipment departs."""
        if shipment not in self.f_loads_finished:
            return

        super().depart(shipment)

        transshipment_port = self._get_departure_transshipment_port(shipment)
        if transshipment_port in self._hc_teus_by_transshipment_port:
            self._hc_teus_by_transshipment_port[transshipment_port].observe_change(-shipment.teu_size)

    # -------------------------------------------------------------------------
    # Port helpers (matching the reference behavior private methods)
    # -------------------------------------------------------------------------

    def _get_arrival_transshipment_port(self, shipment: 'Shipment') -> 'Port':
        """Reference GetArrivalTransshipmentPort: arrival port of current booking segment."""
        current_booking_index = shipment.current_booking_index
        current_booking = None
        for b in shipment.associated_bookings:
            if b.sequence_index == current_booking_index:
                current_booking = b
                break

        if current_booking is None:
            return None

        service_route = current_booking.service_route

        arrival_segment = None
        for seg in service_route.segments:
            if seg.sequence_index == current_booking.arrival_segment_index:
                arrival_segment = seg
                break

        if arrival_segment is None:
            return None

        return arrival_segment.associated_leg.arrival_port

    def _get_departure_transshipment_port(self, shipment: 'Shipment') -> 'Port':
        """Reference GetDepartureTransshipmentPort: departure port of current booking segment."""
        current_booking_index = shipment.current_booking_index
        current_booking = None
        for b in shipment.associated_bookings:
            if b.sequence_index == current_booking_index:
                current_booking = b
                break

        if current_booking is None:
            return None

        service_route = current_booking.service_route

        departure_segment = None
        for seg in service_route.segments:
            if seg.sequence_index == current_booking.departure_segment_index:
                departure_segment = seg
                break

        if departure_segment is None:
            return None

        return departure_segment.associated_leg.departure_port

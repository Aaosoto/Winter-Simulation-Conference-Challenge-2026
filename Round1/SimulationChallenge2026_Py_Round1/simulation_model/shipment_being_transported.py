"""
Shipment Being Transported Activity.

Reference behavior: ActivityHandler<Shipment> with:
  - signal_start(Vessel): adds vessel to p_start_signals, schedules attempt_start
  - signal_finish(Vessel): adds vessel to q_finish_signals, schedules attempt_finish
  - attempt_start: for each P vessel, for each shipment whose current booking
      departs on vessel's next segment and shipment is in r_loads_requested_start,
      set CarryingVessel = vessel, start(shipment)
  - attempt_finish: for each Q vessel, for each D shipment with CarryingVessel==vessel
      and not in vessel.carried_shipments, clear CarryingVessel, finish(shipment)
  - start override: if CurrentBookingIndex==1, record hc_teus_in_transition_by_demand stats
  - depart override: if isLastBooking, subtract TEU from hc_teus_in_transition_by_demand

NOTE: signal_start only accepts Vessel (not Shipment).
Shipment path: SWfL.AO.on_finish → VBS.signal_start(shipment) [via wiring in model.py],
NOT via direct SBfT.signal_start.
"""

from typing import TYPE_CHECKING, Dict

from o2des.common import ActionSet
from o2des.core import HourCounter
from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet

if TYPE_CHECKING:
    from maritime_data_context import (
        MaritimeDataContext, Demand, Shipment, Vessel
    )


class ShipmentBeingTransported(ActivityHandler):
    """
    Represents shipments being transported by vessel.

    start is controlled by vessel signals (load shipments via booking route+segment match).
    finish is controlled by vessel signals (discharge shipments).
    """

    def __init__(self, data_context: 'MaritimeDataContext' = None, seed: int = 0):
        super().__init__(seed=seed, id="ShipmentBeingTransported")

        # Vessel signals for starting/finishing transported shipments
        self._p_start_signals: OrderedSet['Vessel'] = OrderedSet()
        self._q_finish_signals: OrderedSet['Vessel'] = OrderedSet()

        # Statistics - one HourCounter per demand, pre-created so that
        # _creation_time = sim start (= 0), matching the reference behavior's AddHourCounter().
        # Without eager creation, the first shipment to depart would create
        # the demand's counter late, biasing the in-transition TEU average.
        self._hc_teus_in_transition_by_demand: Dict['Demand', HourCounter] = {}
        if data_context is not None:
            for demand in data_context.demands:
                self._hc_teus_in_transition_by_demand[demand] = self.add_hour_counter()

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def p_start_signals(self) -> 'OrderedSet[Vessel]':
        return self._p_start_signals

    @property
    def q_finish_signals(self) -> 'OrderedSet[Vessel]':
        return self._q_finish_signals

    @property
    def hc_teus_in_transition_by_demand(self) -> Dict['Demand', HourCounter]:
        return self._hc_teus_in_transition_by_demand

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    # -------------------------------------------------------------------------
    # signal_start / signal_finish — external control gates
    # -------------------------------------------------------------------------

    def signal_start(self, vessel: 'Vessel') -> None:
        """
        Polymorphic signal entry point (ActivityHandler<Shipment>.signal_start contract).

        The reference implementation has two separate methods:
          - ActivityHandler<Shipment>.RequestStart(Shipment) → r_loads_requested_start
            (called via ConnectTo event flow: SWfL.on_finish → SBfT.RequestStart)
          - SBfT.signal_start(Vessel) → p_start_signals
            (called via signal wiring: VBS.on_start → SBfT.signal_start)

        Python dispatch: Shipment → base class R, Vessel → p_start_signals.
        """
        # Shipment from ConnectTo event flow → base class adds to r_loads_requested_start
        from maritime_data_context.shipment import Shipment as ShipmentClass
        if isinstance(entity := vessel, ShipmentClass):
            ActivityHandler.signal_start(self, entity)
            return
        # Vessel from VBS signal wiring → add to p_start_signals
        if vessel is None:
            return
        if vessel not in self._p_start_signals:
            self._p_start_signals.add(vessel)
            self.schedule(self.attempt_start)

    def signal_finish(self, vessel: 'Vessel') -> None:
        """
        Reference signal_finish(Vessel vessel):
          if q_finish_signals.Add(vessel): Schedule(attempt_finish)
        """
        if vessel is None:
            return
        if vessel not in self._q_finish_signals:
            self._q_finish_signals.add(vessel)
            self.schedule(self.attempt_finish)

    # -------------------------------------------------------------------------
    # attempt_start / attempt_finish — gate logic
    # -------------------------------------------------------------------------

    def attempt_start(self) -> None:
        """
        Reference attempt_start exactly matched:
          foreach vessel in p_start_signals.ToList():
            loadingShipments = vessel.get_loading_shipments_at_next_segment()
            foreach shipment in loadingShipments:
              Require(CarryingVessel == null)
              Require(r_loads_requested_start.Contains(shipment))
              shipment.carrying_vessel = vessel
              start(shipment)
            p_start_signals.Remove(vessel)
        """
        for vessel in list(self._p_start_signals):
            loading_shipments = vessel.get_loading_shipments_at_next_segment()

            for shipment in loading_shipments:
                if shipment.carrying_vessel is not None:
                    continue
                if shipment not in self.r_loads_requested_start:
                    continue

                shipment.carrying_vessel = vessel
                self.start(shipment)

            self._p_start_signals.discard(vessel)

    def attempt_finish(self) -> None:
        """
        Reference attempt_finish:
          foreach vessel in q_finish_signals.ToList():
            var shipmentsToFinish = d_loads_ready_finish
              .Where(s => s.carrying_vessel == vessel && !vessel.carried_shipments.Contains(s))
              .ToList()
            foreach shipment in shipmentsToFinish:
              shipment.carrying_vessel = null
              finish(shipment)
            q_finish_signals.Remove(vessel)
        """
        for vessel in list(self._q_finish_signals):
            shipments_to_finish = [
                s for s in self.d_loads_ready_finish
                if s.carrying_vessel == vessel and s not in vessel.carried_shipments
            ]

            for shipment in shipments_to_finish:
                shipment.carrying_vessel = None
                self.finish(shipment)

            self._q_finish_signals.discard(vessel)

    # -------------------------------------------------------------------------
    # Statistics — TEU in Transition by Demand
    # -------------------------------------------------------------------------

    def start(self, shipment: 'Shipment') -> None:
        """
        Reference start: if CurrentBookingIndex == 1, record TEU in transition stats.
        """
        super().start(shipment)

        if shipment.current_booking_index != 1:
            return

        demand = shipment.demand
        # Counter is pre-created at ctor; fallback handles missing data_context.
        if demand not in self._hc_teus_in_transition_by_demand:
            self._hc_teus_in_transition_by_demand[demand] = self.add_hour_counter()
        self._hc_teus_in_transition_by_demand[demand].observe_change(shipment.teu_size)

    def depart(self, shipment: 'Shipment') -> None:
        """
        Reference depart: if isLastBooking, subtract TEU from transition stats.
        """
        if shipment not in self.f_loads_finished:
            return

        is_last = shipment.is_at_last_booking()

        super().depart(shipment)

        if not is_last:
            return

        demand = shipment.demand
        if demand in self._hc_teus_in_transition_by_demand:
            self._hc_teus_in_transition_by_demand[demand].observe_change(-shipment.teu_size)

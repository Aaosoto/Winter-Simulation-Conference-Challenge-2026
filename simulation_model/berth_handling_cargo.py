"""
Berth Handling Cargo Activity.

Reference behavior: ActivityHandler<Berth> with:
  - p_start_signals: HashSet<Vessel> for vessel start signals
  - T_Duration = (berth, rs) => GetDuration(berth, rs)
  - signal_start(Vessel vessel): adds vessel to P, schedules attempt_start
  - attempt_start: for each vessel in P, if berth in R, sets berth.occupying_vessel = vessel, start(berth)

on_finish (Berth) → BerthIdle.RequestStart(berth)
  [via ConnectTo: BerthHandlingCargo.on_finish → BerthIdle.RequestStart]
  Also: VesselBeingServed.signal_finish(berth) is called by wiring in model.py
"""

import datetime as dt
from typing import TYPE_CHECKING

from o2des.common import ActionSet
from .activity_handler import ActivityHandler
from .ordered_set import OrderedSet

if TYPE_CHECKING:
    from maritime_data_context import (
        Vessel, Berth
    )


class BerthHandlingCargo(ActivityHandler):
    """
    Cargo handling activity at berth.

    start: Triggered when berth finishes berthing and signals vessel.
    Duration: computed from (loaded_teu + discharged_teu) / quay_crane_productivity.
    After finishing, berth returns to idle state (via on_finish → BerthIdle.RequestStart).
    """

    def __init__(self, seed: int = 0):
        super().__init__(seed=seed, id="BerthHandlingCargo")

        # Vessel start signals waiting to trigger cargo handling
        self._p_start_signals: OrderedSet['Vessel'] = OrderedSet()

        # Duration is defined based on berth state
        self._t_duration = lambda berth, rs: self._get_duration(berth, rs)

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

    @property
    def p_start_signals(self) -> 'OrderedSet[Vessel]':
        return self._p_start_signals

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish

    def signal_start(self, vessel: 'Vessel') -> None:
        """
        Polymorphic signal entry point (ActivityHandler<Berth>.signal_start contract).

        The reference implementation has two separate methods:
          - ActivityHandler<Berth>.RequestStart(Berth) → r_loads_requested_start
            (called via ConnectTo event flow: BB.on_finish → BHC.RequestStart)
          - BHC.signal_start(Vessel) → p_start_signals
            (called via signal wiring: VBS.on_start → BHC.signal_start)

        Python dispatch: Berth → base class R, Vessel → p_start_signals.
        """
        # Berth from ConnectTo event flow → base class adds to r_loads_requested_start
        from maritime_data_context.berth import Berth as BerthClass
        if isinstance(entity := vessel, BerthClass):
            ActivityHandler.signal_start(self, entity)
            return
        # Vessel from VBS signal wiring → add to p_start_signals
        if vessel is None:
            return
        if vessel not in self._p_start_signals:
            self._p_start_signals.add(vessel)
            self.schedule(self.attempt_start)

    def attempt_start(self) -> None:
        """
        Reference BerthHandlingCargo.attempt_start:
          if r_loads_requested_start.Count == 0 || p_start_signals.Count == 0: return
          foreach vessel in p_start_signals:
            berth = vessel.current_berth
            if berth not in r_loads_requested_start: continue
            berth.occupying_vessel = vessel
            p_start_signals.Remove(vessel)
            start(berth)
        """
        if not self.r_loads_requested_start or not self._p_start_signals:
            return

        for vessel in list(self._p_start_signals):
            berth = vessel.current_berth
            if berth is None:
                continue
            if berth not in self.r_loads_requested_start:
                continue

            berth.occupying_vessel = vessel
            self._p_start_signals.discard(vessel)
            self.start(berth)

    def _get_duration(self, berth: 'Berth', rs) -> dt.timedelta:
        """
        Reference GetDuration:
          vessel = berth.occupying_vessel
          vesselClass = vessel.vessel_class
          qcCount = max(1, floor(vesselClass.loa / 100))
          dischargingTeu = vessel.get_discharging_shipments_at_current_segment().Sum(s => s.teu_size)
          loadingTeu = vessel.get_loading_shipments_at_next_segment().Sum(s => s.teu_size)
          hours = (dischargingTeu + loadingTeu) / (qcCount * 60)
          return TimeSpan.FromHours(hours)
        """
        vessel = berth.occupying_vessel
        if vessel is None:
            return dt.timedelta(0)

        vessel_class = vessel.vessel_class
        qc_count = max(1, int(vessel_class.loa / 55))
        discharging_teu = sum(
            s.teu_size for s in vessel.get_discharging_shipments_at_current_segment()
        )
        loading_teu = sum(
            s.teu_size for s in vessel.get_loading_shipments_at_next_segment()
        )
        total_teu = discharging_teu + loading_teu
        hours = total_teu / (qc_count * 45.0)
        return dt.timedelta(hours=hours)

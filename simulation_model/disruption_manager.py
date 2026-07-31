"""Runtime application and restoration of planned disruptions."""

import datetime as dt

from o2des.core import Sandbox


class DisruptionManager(Sandbox):
    def __init__(self, data_context, simulation_start: dt.datetime, seed: int = 0):
        super().__init__(seed=seed, uid="DisruptionManager")
        self._data_context = data_context
        self._simulation_start = simulation_start
        self.schedule(self._check_plans)

    def _check_plans(self) -> None:
        now = self.clock_time

        for plan in self._data_context.disruption_plans:
            if plan.start_offset_days is None or plan.duration_days is None:
                continue

            start = self._simulation_start + dt.timedelta(days=plan.start_offset_days)
            end = start + dt.timedelta(days=plan.duration_days)
            active = start <= now < end

            if plan.target_leg is not None:
                plan.target_leg.sailing_time_multiplier = plan.multiplier if active else 1.0

            if plan.target_berth is not None and plan.close_berth:
                plan.target_berth.is_available = not active

        self.schedule(self._check_plans, delay=dt.timedelta(days=1))

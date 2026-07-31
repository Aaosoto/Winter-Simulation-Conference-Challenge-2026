"""
Vessel Generator - schedules all vessels to arrive at simulation start.
"""

import datetime as dt

from o2des.common import ActionSet
from o2des.core import Sandbox

from maritime_data_context import MaritimeDataContext


class VesselGenerator(Sandbox):
    """
    Generates and initializes vessels at simulation start.

    All vessels are scheduled to arrive at TimeSpan.Zero.
    """

    def __init__(
        self,
        data_context: MaritimeDataContext,
        seed: int = 0
    ):
        super().__init__(seed=seed, uid="VesselGenerator")
        self._maritime_data_context = data_context

        # on_finish: event for vessel arrival (wired to VesselAwaitingInstructions)
        self.on_finish = ActionSet(object)

        # Schedule all vessels to arrive at t=0
        for vessel in self._maritime_data_context.vessels:
            self.schedule(self._arrive, delay=dt.timedelta(0), vessel=vessel)

    def _arrive(self, vessel) -> None:
        """Register vessel arrival and signal on_finish."""
        self.on_finish.invoke(vessel)

    def arrive(self, vessel) -> None:
        """Public method to introduce a vessel to the simulation."""
        pass

"""
Berth Generator - schedules all berths to be available at simulation start.
"""

import datetime as dt

from o2des.common import ActionSet
from o2des.core import Sandbox

from maritime_data_context import MaritimeDataContext


class BerthGenerator(Sandbox):
    """
    Generates and initializes berths at simulation start.

    All berths are scheduled to arrive at TimeSpan.Zero.
    """

    def __init__(
        self,
        data_context: MaritimeDataContext,
        seed: int = 0
    ):
        super().__init__(seed=seed, uid="BerthGenerator")
        self._maritime_data_context = data_context

        # on_finish: event for berth arrival (wired to BerthIdle)
        self.on_finish = ActionSet(object)

        # Schedule all berths to arrive at t=0
        for port in self._maritime_data_context.ports:
            for berth in port.berths:
                self.schedule(self._arrive, delay=dt.timedelta(0), berth=berth)

    def _arrive(self, berth) -> None:
        """Register berth arrival and signal on_finish."""
        self.on_finish.invoke(berth)

    def arrive(self, berth) -> None:
        """Public method to introduce a berth to the simulation."""
        pass

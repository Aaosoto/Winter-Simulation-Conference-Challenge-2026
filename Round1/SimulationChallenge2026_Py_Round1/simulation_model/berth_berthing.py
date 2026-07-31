"""
Berth Berthing Activity.

Reference behavior: ActivityHandler<Berth> with T_Duration = 3 hours.
No custom start/finish/attempt_start/attempt_finish overrides.
State transitions: R → S → D → F → exit.
on_finish → BerthHandlingCargo.signal_start(berth), BerthIdle.signal_start(berth)
"""

import datetime as dt
from typing import TYPE_CHECKING

from o2des.common import ActionSet
from .activity_handler import ActivityHandler

if TYPE_CHECKING:
    pass


class BerthBerthing(ActivityHandler):
    """
    Represents the berthing process (vessel positioning at berth).

    Duration = 3 hours fixed.
    State machine (ActivityHandler<Berth>):
      R → S → D → F → exit (via ConnectTo wiring)

    on_finish → BerthHandlingCargo.signal_start(berth)
             → BerthIdle.signal_start(berth)
    """

    def __init__(self, seed: int = 0):
        super().__init__(seed=seed, id="BerthBerthing")

        # Fixed 3-hour berthing duration
        self._t_duration = lambda berth, rs: dt.timedelta(hours=3.0)

        # Backward compat: state shadow attributes (not used for base class state)
        self._r_loads_requested_start = self.__dict__['_r_lrs']
        self._d_loads_ready_finish = self.__dict__['_d_lrf']
        self._f_loads_finished = self.__dict__['_f_lf']

        self._on_start = ActionSet(object)
        self._on_finish = ActionSet(object)

    @property
    def on_start(self) -> ActionSet:
        return self._on_start

    @property
    def on_finish(self) -> ActionSet:
        return self._on_finish
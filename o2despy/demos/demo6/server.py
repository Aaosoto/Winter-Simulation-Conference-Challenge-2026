from __future__ import annotations

import datetime as dt

from o2des.common import ActionSet
from o2des.core import Sandbox
from o2des.utils import Distributions as Dist


class Server(Sandbox):

    def __init__(self, capacity: int, hourly_service_rate: float, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self.capacity = capacity
        self.hourly_service_rate = hourly_service_rate
        # Dynamics
        self.number_in_service = 0
        # Events
        self.on_change_accessibility: ActionSet = ActionSet(bool)

    def start(self) -> None:
        if self.number_in_service >= self.capacity:
            raise RuntimeError("Insufficient vacancy")
        self.number_in_service += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tStart.  \t\t#In-Service: {self.number_in_service}")
        delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_service_rate)
        self.schedule(self.finish, delay=dt.timedelta(hours=delay))
        if self.number_in_service == self.capacity:
            self.schedule(self.change_accessibility)

    def finish(self) -> None:
        self.number_in_service -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tFinish. \t\t#In-Service: {self.number_in_service}")
        if self.number_in_service == self.capacity - 1:
            self.schedule(self.change_accessibility)

    def change_accessibility(self) -> None:
        self.on_change_accessibility.invoke(self.number_in_service < self.capacity)

from __future__ import annotations

import datetime as dt

from o2des.common import ActionSet
from o2des.core import Sandbox
from o2des.utils import Distributions as Dist


class Server(Sandbox):

    def __init__(self, capacity: int, hourly_service_rate: float, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self.capacity: int = capacity
        self.hourly_service_rate: float = hourly_service_rate
        # Dynamics
        self.number_pending: int = 0
        self.number_in_service: int = 0
        # Events
        self.on_start: ActionSet = ActionSet()
        self.on_finish: ActionSet = ActionSet()

    def request_to_start(self) -> None:
        self.number_pending += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tRequestToStart. \t"
              f"#Pending: {self.number_pending}. #In-Service: {self.number_in_service}")
        if self.number_in_service < self.capacity:
            self.start()

    def start(self) -> None:
        self.number_pending -= 1
        self.number_in_service += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tStart.  \t\t"
              f"#Pending: {self.number_pending}. #In-Service: {self.number_in_service}")
        delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_service_rate)
        self.schedule(self.finish, delay=dt.timedelta(hours=round(delay, 2)))
        self.on_start.invoke()

    def finish(self) -> None:
        self.number_in_service -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tFinish. \t\t"
              f"#Pending: {self.number_pending}. #In-Service: {self.number_in_service}")
        if self.number_pending > 0:
            self.start()
        self.on_finish.invoke()

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
        self.number_in_service: int = 0
        self.number_pending_depart: int = 0
        self.able_to_depart: bool = True
        # Events
        self.on_change_accessibility: ActionSet = ActionSet(bool)
        self.on_depart: ActionSet = ActionSet()

    def start(self) -> None:
        if self.number_in_service + self.number_pending_depart >= self.capacity:
            raise RuntimeError("Insufficient vacancy")
        self.number_in_service += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tStart.  \t\t"
              f"#In-Service: {self.number_in_service}. #Pending-Depart: {self.number_pending_depart}")
        delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_service_rate)
        self.schedule(self.finish, delay=dt.timedelta(hours=round(delay,2)))
        if self.number_in_service == self.capacity:
            self.change_accessibility()

    def finish(self) -> None:
        self.number_in_service -= 1
        self.number_pending_depart += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tFinish. \t\t"
              f"#In-Service: {self.number_in_service}. #Pending-Depart: {self.number_pending_depart}")
        if self.able_to_depart:
            self.depart()

    def depart(self) -> None:
        self.number_pending_depart -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tDepart. \t\t"
              f"#In-Service: {self.number_in_service}. #Pending-Depart: {self.number_pending_depart}")
        if self.number_in_service + self.number_pending_depart == self.capacity - 1:
            self.change_accessibility()
        self.on_depart.invoke()

    def update_to_depart(self, able_to_depart: bool) -> None:
        self.able_to_depart = able_to_depart
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tUpdateToDepart. \t"
              f"AbleToDepart: {self.able_to_depart}")
        if self.able_to_depart and self.number_pending_depart > 0:
            self.depart()

    def change_accessibility(self) -> None:
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tChangeAccessibility. \t"
              f"#In_Service: {self.number_in_service}")
        able = self.number_in_service + self.number_pending_depart < self.capacity
        self.on_change_accessibility.invoke(able)
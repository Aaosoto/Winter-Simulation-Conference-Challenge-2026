from __future__ import annotations

import datetime as dt

from o2des.core import Sandbox
from o2des.utils import Distributions as Dist
from o2des.utils import LogUtils


class MMcQueue(Sandbox):

    def __init__(
        self,
        hourly_arrival_rate: float,
        hourly_service_rate: float,
        capacity: int,
        seed: int = 0,
    ) -> None:
        super().__init__(seed=seed)
        # Statics
        self.hourly_arrival_rate: float = hourly_arrival_rate
        self.hourly_service_rate: float = hourly_service_rate
        self.capacity: int = capacity
        # Dynamics
        self.in_queue: int = 0
        self.in_service: int = 0
        # Events
        self.schedule(self.arrive, delay=dt.timedelta(seconds=0))

    def arrive(self) -> None:
        if self.in_service < self.capacity:
            self.in_service += 1
            print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tArrive and Start Service "
                  f"(In-Queue: {self.in_queue}, In-Service: {self.in_service})")
            delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_service_rate)
            self.schedule(self.depart, delay=dt.timedelta(hours=round(delay, 2)))
        else:
            self.in_queue += 1
            print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tArrive and Join Queue    "
                  f"(In-Queue: {self.in_queue}, In-Service: {self.in_service})")
        delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_arrival_rate)
        self.schedule(self.arrive, delay=dt.timedelta(hours=round(delay, 2)))

    def depart(self) -> None:
        if self.in_queue > 0:
            self.in_queue -= 1
            print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tDepart and Start Service "
                  f"(In-Queue: {self.in_queue}, In-Service: {self.in_service})")
            delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_service_rate)
            self.schedule(self.depart, delay=dt.timedelta(hours=round(delay, 2)))
        else:
            self.in_service -= 1
            print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tDepart                   "
                  f"(In-Queue: {self.in_queue}, In-Service: {self.in_service})")


def run_sim():
    LogUtils.get_logger().reset()
    sim = MMcQueue(hourly_arrival_rate=5, hourly_service_rate=8, capacity=2, seed=0)
    sim.run(duration=dt.timedelta(hours=30))
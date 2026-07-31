from __future__ import annotations

import datetime as dt

from o2des.core import Sandbox
from o2des.utils import Distributions as Dist
from o2des.utils import LogUtils


class HelloWorld(Sandbox):

    def __init__(
        self,
        hourly_arrival_rate: float,
        seed: int = 0,
    ) -> None:
        super().__init__(seed=seed)
        # Statics
        self._hourly_arrival_rate: float = hourly_arrival_rate
        # Dynamics
        self._count: int = 0
        # Events
        self.schedule(self.arrive)

    def arrive(self) -> None:
        self._count += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tHello World #{self._count}!")
        delay = Dist.Exponential.sample(self._default_rs, beta=self._hourly_arrival_rate)
        self.schedule(self.arrive, delay=dt.timedelta(hours=round(delay, 2)))


def run_sim() -> None:
    LogUtils.get_logger().reset()
    sim = HelloWorld(10, seed=3)
    sim.warmup(till=dt.datetime(year=1, month=1, day=1, hour=0, minute=0, second=0))
    sim.run(event_count=10)
    # sim.run(terminate=dt.datetime(year=1, month=1, day=2, hour=0, minute=0))
    # sim.run(duration=dt.timedelta(hours=50))
    # sim.run(speed=10)
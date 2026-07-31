from __future__ import annotations

import datetime as dt

from o2des.core import Sandbox
from o2des.utils import Distributions as Dist
from o2des.utils import LogUtils


class BirthDeath(Sandbox):

    def __init__(
        self,
        hourly_birth_rate: float,
        hourly_death_rate: float,
        seed: int = 0,
    ) -> None:
        super().__init__(seed=seed)
        # Statics
        self.hourly_birth_rate: float = hourly_birth_rate
        self.hourly_death_rate: float = hourly_death_rate
        # Dynamics
        self.population: int = 0
        # Events
        self.schedule(self.birth)

    def birth(self) -> None:
        self.population += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tBirth (Population: {self.population})")
        delay_birth = Dist.Exponential.sample(self._default_rs, beta=self.hourly_birth_rate)
        delay_death = Dist.Exponential.sample(self._default_rs, beta=self.hourly_death_rate)
        self.schedule(self.birth, delay=dt.timedelta(hours=round(delay_birth, 2)))
        self.schedule(self.death, delay=dt.timedelta(hours=round(delay_death, 2)))

    def death(self) -> None:
        self.population -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tDeath (Population: {self.population})")


def run_sim() -> None:
    LogUtils.get_logger().reset()
    sim = BirthDeath(12, 4, seed=0)
    sim.warmup(till=dt.datetime(year=1, month=1, day=1, hour=0, minute=0, second=0))
    sim.run(event_count=10)
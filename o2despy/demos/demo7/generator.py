from __future__ import annotations

import datetime as dt

from o2des.common import ActionSet
from o2des.core import Sandbox
from o2des.utils import Distributions as Dist


class Generator(Sandbox):

    def __init__(self, hourly_rate: float, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self.hourly_rate: float = hourly_rate
        # Dynamics
        self.count: int = 0
        # Events
        self.on_generate: ActionSet = ActionSet()
        self.schedule(self.generate)

    def generate(self) -> None:
        if self.count > 0:
            print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)}\tGenerate. \t\tCount: {self.count}")
            self.on_generate.invoke()
        self.count += 1
        delay = Dist.Exponential.sample(self._default_rs, beta=self.hourly_rate)
        self.schedule(self.generate, delay=dt.timedelta(hours=round(delay, 2)))

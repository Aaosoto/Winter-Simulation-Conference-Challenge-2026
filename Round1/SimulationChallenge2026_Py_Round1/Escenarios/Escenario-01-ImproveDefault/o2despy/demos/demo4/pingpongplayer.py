from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from o2des.common import ActionSet
from o2des.core import Sandbox
from o2des.utils import Distributions as Dist


@dataclass
class Statics:
    index: int
    delay_time_expected: float
    delay_time_CV: float


class PingPongPlayer(Sandbox):

    Statics = Statics

    def __init__(
        self,
        config: Statics,
        seed: int = 0,
    ) -> None:
        super().__init__(seed=seed)
        # Statics
        self._config: Statics = config
        # Dynamics
        self._count: int = 0
        # Events
        self.on_send: ActionSet = ActionSet()

    @property
    def config(self) -> Statics:
        return self._config

    @property
    def count(self) -> int:
        return self._count

    def send(self) -> None:
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tPlayer#{self._config.index}, Send. \tCount: {self._count}")
        self.on_send.invoke()

    def receive(self) -> None:
        self._count += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\tPlayer#{self._config.index}, Receive. \tCount: {self._count}")
        delay = Dist.Gamma.sample(
            self._default_rs,
            mean=self._config.delay_time_expected,
            cv=self._config.delay_time_CV)
        self.schedule(self.send, delay=dt.timedelta(seconds=round(delay, 2)))

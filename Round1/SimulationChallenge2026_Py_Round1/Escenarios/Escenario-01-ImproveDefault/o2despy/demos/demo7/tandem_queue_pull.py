from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from o2des.core import Sandbox
from o2des.utils import LogUtils

from .generator import Generator
from .queue_ import Queue
from .server import Server


@dataclass
class Statics:
    capacity: int
    hourly_arrival_rate: float
    hourly_service_rate: float


class TandemQueuePull(Sandbox):

    Statics = Statics

    def __init__(self, config: Statics, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self._config: Statics = config
        # Dynamics
        self.generator: Generator = self.add_child(
            Generator(self._config.hourly_arrival_rate, seed=seed))
        self.queue1: Queue = self.add_child(
            Queue(seed=seed))
        self.server1: Server = self.add_child(
            Server(self._config.capacity, self._config.hourly_service_rate, seed=seed))
        self.queue2: Queue = self.add_child(
            Queue(seed=seed))
        self.server2: Server = self.add_child(
            Server(self._config.capacity, self._config.hourly_service_rate, seed=seed))

        # Connect for 1st Queue & Server
        self.generator.on_generate += self.queue1.enqueue
        self.generator.on_generate += self.server1.request_to_start
        self.server1.on_start += self.queue1.dequeue

        # Connect for 2nd Queue & Server
        self.server1.on_finish += self.queue2.enqueue
        self.server1.on_finish += self.server2.request_to_start
        self.server2.on_start += self.queue2.dequeue

    @property
    def config(self) -> Statics:
        return self._config


def run_sim() -> None:
    LogUtils.get_logger().reset()
    config = TandemQueuePull.Statics(
        capacity=1,
        hourly_arrival_rate=4,
        hourly_service_rate=5,
    )
    sim = TandemQueuePull(config=config, seed=0)
    sim.run(event_count=10)
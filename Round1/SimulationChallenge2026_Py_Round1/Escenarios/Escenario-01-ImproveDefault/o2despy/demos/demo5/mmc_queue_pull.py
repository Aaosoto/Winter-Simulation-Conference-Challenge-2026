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


class MMcQueuePull(Sandbox):

    Statics = Statics

    def __init__(self, config: Statics, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self._config: Statics = config
        # Dynamics
        self.generator: Generator = self.add_child(
            Generator(self._config.hourly_arrival_rate, seed=seed))
        self.queue: Queue = self.add_child(
            Queue(seed=seed))
        self.server: Server = self.add_child(
            Server(self._config.capacity, self._config.hourly_service_rate, seed=seed))
        # Events
        self.generator.on_generate += self.queue.enqueue
        self.generator.on_generate += self.server.request_to_start
        self.server.on_start += self.queue.dequeue

    @property
    def config(self) -> Statics:
        return self._config


def run_sim() -> None:
    LogUtils.get_logger().reset()
    config = MMcQueuePull.Statics(
        capacity=1,
        hourly_arrival_rate=4,
        hourly_service_rate=5,
    )
    sim = MMcQueuePull(config=config, seed=0)
    sim.run(event_count=10)
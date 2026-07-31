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
    queue_capacity: int
    server_capacity: int
    hourly_arrival_rate: float
    hourly_service_rate: float


class ConstrainedTandemQueuePull(Sandbox):

    Statics = Statics

    def __init__(self, config: Statics, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self._config: Statics = config
        # Dynamics
        self.generator: Generator = self.add_child(
            Generator(self._config.hourly_arrival_rate, seed=seed))
        self.queue1: Queue = self.add_child(
            Queue(self._config.queue_capacity, seed=seed))
        self.server1: Server = self.add_child(
            Server(self._config.server_capacity, self._config.hourly_service_rate, seed=seed))
        self.queue2: Queue = self.add_child(
            Queue(self._config.queue_capacity, seed=seed))
        self.server2: Server = self.add_child(
            Server(self._config.server_capacity, self._config.hourly_service_rate, seed=seed))

        # Connect for 1st Queue & Server
        self.generator.on_generate += self.queue1.request_to_enqueue
        self.generator.on_generate += self.server1.request_to_start
        self.server1.on_start += self.queue1.dequeue

        # Connects for 2nd Queue & Server
        self.server1.on_ready_to_finish += self.queue2.request_to_enqueue
        self.server1.on_ready_to_finish += self.server2.request_to_start
        self.queue2.on_enqueue += self.server1.finish
        self.server2.on_start += self.queue2.dequeue

        # Enclose 2nd Server
        self.server2.on_ready_to_finish += self.server2.finish


def run_sim() -> None:
    LogUtils.get_logger().reset()
    config = ConstrainedTandemQueuePull.Statics(
        queue_capacity=2,
        server_capacity=1,
        hourly_arrival_rate=4,
        hourly_service_rate=5,
    )
    sim = ConstrainedTandemQueuePull(config=config, seed=0)
    sim.run(event_count=10)
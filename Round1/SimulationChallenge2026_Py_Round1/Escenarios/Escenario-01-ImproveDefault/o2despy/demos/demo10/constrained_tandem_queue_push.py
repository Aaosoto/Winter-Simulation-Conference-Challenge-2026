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


class ConstrainedTandemQueuePush(Sandbox):

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
        self.generator.on_generate += self.queue1.enqueue
        self.queue1.on_dequeue += self.server1.start
        self.server1.on_change_accessibility += self.queue1.update_to_dequeue

        # Connects for 2nd Queue & Server
        self.server1.on_depart += self.queue2.enqueue
        self.queue2.on_dequeue += self.server2.start
        self.queue2.on_change_accessibility += self.server1.update_to_depart
        self.server2.on_change_accessibility += self.queue2.update_to_dequeue


def run_sim() -> None:
    LogUtils.get_logger().reset()
    config = ConstrainedTandemQueuePush.Statics(
        queue_capacity=2,
        server_capacity=1,
        hourly_arrival_rate=4,
        hourly_service_rate=5,
    )
    sim = ConstrainedTandemQueuePush(config=config)
    sim.run(event_count=10)
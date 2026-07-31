from __future__ import annotations

import datetime as dt

from o2des.common import ActionSet
from o2des.core import Sandbox


class Queue(Sandbox):

    def __init__(self, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Dynamics
        self.number_waiting: int = 0
        self.able_to_dequeue: bool = True
        # Events
        self.on_dequeue: ActionSet = ActionSet()

    def enqueue(self) -> None:
        self.number_waiting += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tEnqueue. \t\t#Waiting: {self.number_waiting}")
        if self.able_to_dequeue:
            self.dequeue()

    def update_to_dequeue(self, able_to_dequeue: bool) -> None:
        self.able_to_dequeue = able_to_dequeue
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tUpdateToDequeue. \tAbleToDequeue: {self.able_to_dequeue}")
        if self.able_to_dequeue and self.number_waiting > 0:
            self.dequeue()

    def dequeue(self) -> None:
        self.number_waiting -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tDequeue. \t\t#Waiting: {self.number_waiting}")
        self.on_dequeue.invoke()

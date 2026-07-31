from __future__ import annotations

from o2des.common import ActionSet
from o2des.core import Sandbox


class Queue(Sandbox):

    def __init__(self, capacity: int, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Statics
        self.capacity: int = capacity
        # Dynamics
        self.number_waiting: int = 0
        self.able_to_dequeue: bool = True
        # Events
        self.on_dequeue: ActionSet = ActionSet()
        self.on_change_accessibility: ActionSet = ActionSet(bool)

    def enqueue(self) -> None:
        self.number_waiting += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tEnqueue. \t\t"
              f"#Waiting: {self.number_waiting}")
        self.schedule(self.attempt_to_dequeue)
        if self.number_waiting == self.capacity:
            self.change_accessibility()

    def update_to_dequeue(self, able_to_dequeue: bool) -> None:
        self.able_to_dequeue = able_to_dequeue
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tUpdateToDequeue. \t"
              f"AbleToDequeue: {self.able_to_dequeue}")
        if self.able_to_dequeue and self.number_waiting > 0:
            self.dequeue()

    def attempt_to_dequeue(self) -> None:
        if self.able_to_dequeue and self.number_waiting > 0:
            self.dequeue()

    def dequeue(self) -> None:
        self.number_waiting -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tDequeue. \t\t"
              f"#Waiting: {self.number_waiting}")
        if self.number_waiting == self.capacity - 1:
            self.change_accessibility()
        self.on_dequeue.invoke()

    def change_accessibility(self) -> None:
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tChangeAccessibility. \t"
              f"#Waiting: {self.number_waiting}")
        able = self.number_waiting < self.capacity
        self.on_change_accessibility.invoke(able)
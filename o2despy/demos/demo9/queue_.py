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
        self.number_pending: int = 0
        # Events
        self.on_enqueue: ActionSet = ActionSet()

    def request_to_enqueue(self) -> None:
        self.number_pending += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tRequestToEnqueue. \t"
              f"#Pending Queue: {self.number_pending}. #Waiting: {self.number_waiting}.")
        if self.number_waiting < self.capacity:
            self.enqueue()

    def enqueue(self) -> None:
        self.number_pending -= 1
        self.number_waiting += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tEnqueue. \t\t"
              f"#Pending Queue: {self.number_pending}. #Waiting: {self.number_waiting}.")
        self.on_enqueue.invoke()

    def dequeue(self) -> None:
        self.number_waiting -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tDequeue. \t\t"
              f"#Pending Queue: {self.number_pending}. #Waiting: {self.number_waiting}.")
        if self.number_pending > 0:
            self.enqueue()

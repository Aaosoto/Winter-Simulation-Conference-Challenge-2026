from __future__ import annotations

from o2des.core import Sandbox


class Queue(Sandbox):

    def __init__(self, seed: int = 0) -> None:
        super().__init__(seed=seed)
        # Dynamics
        self.number_waiting: int = 0

    def enqueue(self) -> None:
        self.number_waiting += 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tEnqueue. \t\t#Waiting: {self.number_waiting}")

    def dequeue(self) -> None:
        self.number_waiting -= 1
        print(f"{self.clock_time:%Y-%m-%d %H:%M:%S.%f}\t{str(self)} \tDequeue. \t\t#Waiting: {self.number_waiting}")
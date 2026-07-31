import datetime
import math
import random
import time
from datetime import timedelta

from o2des.core import Sandbox
from o2des.standard.generator import Generator
from o2des.standard.load import Load
from o2des.standard.queue_ import Queue
from o2des.standard.server import Server


class TandemQueue(Sandbox):

    def __init__(self, arr_rate, svc_rate1, svc_rate2, buffer_q_size, seed=0):
        super().__init__()
        self.hourly_arrival_rate = arr_rate
        self.hourly_service_rate1 = svc_rate1
        self.hourly_service_rate2 = svc_rate2
        self.buffer_q_size = buffer_q_size
        self.seed = seed

        self.generator = self.add_child(Generator(inter_arrival_time=timedelta(seconds=round(random.expovariate(1 / self.hourly_arrival_rate)))))
        self.queue1 = self.add_child(Queue(capacity=math.inf, id="Queue1"))
        self.server1 = self.add_child(Server(capacity=1, service_time=timedelta(seconds=round(random.expovariate(1 / self.hourly_service_rate1))), id="Server1"))
        self.queue2 = self.add_child(Queue(capacity=self.buffer_q_size, id="Queue2"))
        self.server2 = self.add_child(Server(capacity=1, service_time=timedelta(seconds=round(random.expovariate(1 / self.hourly_service_rate2))), id="Server2"))

        self.generator.on_arrive.add_event_method((self.queue1.rqst_enqueue, Load()))
        self.generator.on_arrive.add_event_method(self.arrive)

        self.queue1.on_enqueued.add_event_method(self.server1.rqst_start)
        self.server1.on_started.add_event_method(self.queue1.dequeue)

        self.server1.on_ready_to_depart.add_event_method(self.queue2.rqst_enqueue)
        self.queue2.on_enqueued.add_event_method(self.server1.depart)

        self.queue2.on_enqueued.add_event_method(self.server2.rqst_start)
        self.server2.on_started.add_event_method(self.queue2.dequeue)

        self.server2.on_ready_to_depart.add_event_method(self.server2.depart)
        self.server2.on_ready_to_depart.add_event_method(self.depart)

        self.hc_in_system = self.add_hour_counter()

        self.generator.start()

    # region Events / Methods
    def arrive(self):
        print("TandemQueue Arrive.")
        self.hc_in_system.observe_change(1, self.clock_time)

    def depart(self):
        print("TandemQueue Depart.")
        self.hc_in_system.observe_change(-1, self.clock_time)


if __name__ == '__main__':
    run_code = 'O2DESPy Tandem Queue'
    start_time = time.time()

    # Demo 1
    sim = TandemQueue(arr_rate=1, svc_rate1=1, svc_rate2=1, buffer_q_size=10)
    hc1 = sim.add_hour_counter()
    sim.run(duration=datetime.timedelta(seconds=30))

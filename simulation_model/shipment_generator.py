"""
Shipment Generator - generates shipments using Negative Binomial TEU size and Exponential interarrival.

Reference behavior: Generator<Shipment> with:
  - MeanShipmentsPerDay default = 10 (not 10.0)
  - _nextShipmentIndex++ (post-increment, assigned before increment)
  - Zero-TEU samples skip shipment creation after scheduling the next attempt
  - arrive(shipment) called last (after Schedule)
  - null check via ArgumentNullException
  - Exponential.Sample(rate) + NegativeBinomial.Sample
"""

import datetime as dt

from o2des.utils.dotnet_distributions import DotNetExponential, DotNetNegativeBinomial

from maritime_data_context import MaritimeDataContext
from maritime_data_context.shipment import Shipment
from .generator import Generator


class ShipmentGenerator(Generator):
    """
    Generates shipments based on demand TEU requirements.

    Uses Negative Binomial distribution for TEU size per shipment and
    Exponential distribution for interarrival time.
    """

    def __init__(
        self,
        data_context: MaritimeDataContext,
        mean_shipments_per_day: float = 10,
        shipment_teu_dispersion: float = 2.0,
        seed: int = 0
    ):
        if data_context is None:
            raise ValueError("data_context cannot be None")

        if mean_shipments_per_day <= 0:
            raise ValueError("Mean shipments per day must be positive.")
        if shipment_teu_dispersion <= 0:
            raise ValueError("Shipment TEU dispersion must be positive.")

        self._maritime_data_context = data_context
        self._mean_shipments_per_day = mean_shipments_per_day
        self._shipment_teu_dispersion = shipment_teu_dispersion
        self._next_shipment_index = 1

        super().__init__(id="ShipmentGenerator", seed=seed)

        # Schedule initial generation for all demands
        for demand in self._maritime_data_context.demands:
            self.schedule(self._generate, delay=dt.timedelta(days=self._next_interarrival_time()), demand=demand)

    def _next_interarrival_time(self) -> float:
        """Sample exponential interarrival time in days."""
        # Reference: Exponential.Sample(DefaultRS, MeanShipmentsPerDay)
        # In reference implementation/MathNet 5.0.0 the named parameter 'rate' actually behaves as
        # a 'mean' / scale (the dll computes -Log(u) / rate). We pass
        # MeanShipmentsPerDay directly to match Reference byte-for-byte.
        return DotNetExponential.sample(self._default_rs, self._mean_shipments_per_day)

    def _sample_shipment_teu_size(self, expected_teu_per_shipment: float) -> int:
        """Sample shipment TEU size from Negative Binomial distribution."""
        if expected_teu_per_shipment <= 0:
            return 0
        return DotNetNegativeBinomial.sample(
            self._default_rs,
            mean=expected_teu_per_shipment,
            dispersion=self._shipment_teu_dispersion,
        )

    def _generate(self, demand) -> None:
        """Generate a single shipment for the given demand."""
        if demand is None:
            raise ValueError("demand cannot be None")

        expected_teu_per_shipment = demand.annual_teus / 365.0 / self._mean_shipments_per_day
        teu_size = self._sample_shipment_teu_size(expected_teu_per_shipment)

        # Schedule next shipment for this demand
        self.schedule(self._generate, delay=dt.timedelta(days=self._next_interarrival_time()), demand=demand)

        # A zero sample represents a generation opportunity with no cargo.
        if teu_size == 0:
            return

        shipment = Shipment(
            index=self._next_shipment_index,
            teu_size=teu_size,
            demand=demand,
            current_storage_port=demand.origin_port,
            generated_time=self.clock_time,
        )
        self._next_shipment_index += 1

        demand.shipments.append(shipment)
        demand.origin_port.shipments_in_storage.append(shipment)

        # Invoke arrival (Reference: arrive(shipment) called last, after Schedule)
        self.arrive(shipment)

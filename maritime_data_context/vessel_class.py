"""
Represents a vessel class with capacity and sailing characteristics.

A vessel class defines the TEU capacity, sailing speed, and length
overall of vessels belonging to that class.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .vessel import Vessel


class VesselClass:
    def __init__(
        self,
        name: str = "",
        teu_capacity: int = 0,
        sailing_speed: float = 0.0,
        loa: float = 0.0
    ):
        self.name = name
        self.teu_capacity = teu_capacity
        self.sailing_speed = sailing_speed
        self.loa = loa  # Length Overall in meters
        self.vessels: List['Vessel'] = []

    def __repr__(self):
        return f"{self.name} | {self.teu_capacity} TEU | {self.loa} m"
"""
Represents a quay berth at a port for vessel loading/unloading operations.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .port import Port


class Berth:
    def __init__(self, index: int = 0, port: 'Port' = None):
        self.index = index
        self.port = port
        self.occupying_vessel = None  # type: Vessel | None
        self.is_available = True

    def __repr__(self):
        return f"{self.port.name}-Berth-{self.index}"

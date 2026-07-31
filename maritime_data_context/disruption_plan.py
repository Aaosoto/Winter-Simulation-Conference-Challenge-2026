"""A simulation-relative disruption applied to a sailing leg or berth."""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .berth import Berth
    from .leg import Leg


class DisruptionPlan:
    def __init__(
        self,
        target_leg: Optional['Leg'] = None,
        target_berth: Optional['Berth'] = None,
        start_offset_days: Optional[float] = None,
        duration_days: Optional[float] = None,
        multiplier: float = 1.0,
        close_berth: bool = False,
    ):
        self.target_leg = target_leg
        self.target_berth = target_berth
        self.start_offset_days = start_offset_days
        self.duration_days = duration_days
        self.multiplier = multiplier
        self.close_berth = close_berth

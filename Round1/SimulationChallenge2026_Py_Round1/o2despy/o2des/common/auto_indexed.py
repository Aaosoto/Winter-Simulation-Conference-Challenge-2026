from __future__ import annotations

from abc import ABC
from typing import Any, ClassVar, Final


class AutoIndexed(ABC):
    """
    Reusable capability that assigns a sequential unique index to each instance.
    """

    _count: ClassVar[int] = 0
    """Class-level counter shared by all instances of the same concrete class."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.__class__._count += 1
        self._index: Final[int] = self.__class__._count
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}#{self._index}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}#{self._index}"

    @property
    def index(self) -> int:
        """
        Read-only unique index in sequence for all instances of the module.
        """
        return self._index

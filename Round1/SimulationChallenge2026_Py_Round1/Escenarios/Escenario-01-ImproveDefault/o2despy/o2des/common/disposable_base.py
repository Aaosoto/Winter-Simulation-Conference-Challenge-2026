from __future__ import annotations

from abc import ABC, abstractmethod


class IDisposable(ABC):
    """
    Disposable interface.
    """

    @abstractmethod
    def dispose(self) -> None:
        """
        Disposal of the object, releasing any resources or performing cleanup as needed.
        """
        ...

from __future__ import annotations

from abc import ABC, abstractmethod


class IAssets(ABC):

    @property
    @abstractmethod
    def uid(self) -> str:
        """
        Tag of the instance of the module.
        """
        ...

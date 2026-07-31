from __future__ import annotations

import os
from abc import ABC
from typing import ClassVar

from o2des.utils import LogUtils


class Loggable(ABC):
    """
    Reusable capability for shared logging support.
    """

    _output_dir: ClassVar[str | None] = None
    """Output directory path shared across all simulation objects."""

    _logger: ClassVar[LogUtils.UnifiedLogger] = LogUtils.get_logger()
    """Logger shared across all simulation objects."""

    @classmethod
    def get_output_dir(cls) -> str | None:
        """
        Retrieve the shared output directory path.
        """
        return cls._output_dir

    @classmethod
    def set_output_dir(cls, output_dir: str | None) -> None:
        """
        Configure the output directory for all simulation objects.

        Create the directory if it doesn't exist.

        Parameters
        ----------
        output_dir : str | None
            Output directory path. If None, output directory is unset.
        """
        cls._output_dir = output_dir
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

    @classmethod
    def get_logger(cls) -> LogUtils.UnifiedLogger | None:
        """
        Retrieve the shared logger.
        """
        return cls._logger

    @classmethod
    def set_logger(cls, new_logger: LogUtils.UnifiedLogger) -> None:
        """
        Configure the logger for all simulation objects.

        Parameters
        ----------
        new_logger : LogUtils.UnifiedLogger
            Logger instance for centralized logging.
        """
        if not isinstance(new_logger, LogUtils.UnifiedLogger):
            raise TypeError(f"new_logger must be an instance of UnifiedLogger, got {type(new_logger)}")
        cls._logger = new_logger

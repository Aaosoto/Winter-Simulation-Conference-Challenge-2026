from __future__ import annotations

from o2des.utils import OutputUtils


class HourCounterLogger:
    """
    Handles log file recording for HourCounter observations.
    """

    def __init__(self, tag: str, output_dir: str) -> None:
        """
        Initialise the logger and open the log file immediately.

        Parameters
        ----------
        tag : str
            Identifier used as the log file name.
        output_dir : str
            Directory path for storing the log file.
        """
        self._tag: str = tag
        self._recorder: OutputUtils.OutputRecorder = OutputUtils.OutputRecorder(tag)
        self._recorder.initialize(output_dir, ["Hours", "Count", "Remark"])

    @property
    def log_file(self) -> str | None:
        """
        Path to the log file, or None if the recorder is not set up.
        """
        return self._recorder.output_file if self._recorder else None

    def reset(self) -> None:
        """
        Reset the log recorder (e.g., after a warm-up period).
        """
        if self._recorder:
            self._recorder.reset()

    def log(self, total_hours: float, count: float, remark: str = "") -> None:
        """
        Write an observation record to the log file.

        Parameters
        ----------
        total_hours : float
            Cumulative active hours since initialisation.
        count : float
            Current count value.
        remark : str, optional
            Additional annotation for the log entry.
        """
        if not self._recorder:
            return
        self._recorder.record_dict({"Hours": total_hours, "Count": count, "Remark": remark})

"""Shared helpers for checking the runtime status of disruption plans."""

import datetime as dt


def is_disruption_active(data_context, current_time: dt.datetime) -> bool:
    """Return whether at least one configured disruption is active."""
    for plan in data_context.disruption_plans:
        if plan.start_offset_days is None or plan.duration_days is None:
            continue

        start_time = dt.datetime.min + dt.timedelta(days=plan.start_offset_days)
        end_time = start_time + dt.timedelta(days=plan.duration_days)
        if start_time <= current_time < end_time:
            return True

    return False

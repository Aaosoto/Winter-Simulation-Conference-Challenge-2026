from __future__ import annotations

import stat


class FileIoConfig:
    """Configuration constants for file I/O operations."""

    PERMISSION_MODE: int = stat.S_IWUSR | stat.S_IRUSR
    """File permission mode (0o600: owner read/write only)."""

    TEXT_ENCODING: str = 'utf-8-sig'
    """Text encoding with BOM signature support for reading both BOM-marked and plain UTF-8 files."""

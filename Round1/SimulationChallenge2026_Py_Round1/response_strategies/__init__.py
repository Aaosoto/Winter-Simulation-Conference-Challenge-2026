"""Contestant and fallback response strategies."""

from .default_strategy import DefaultStrategy
from .user_strategy import UserStrategy

__all__ = ["DefaultStrategy", "UserStrategy"]

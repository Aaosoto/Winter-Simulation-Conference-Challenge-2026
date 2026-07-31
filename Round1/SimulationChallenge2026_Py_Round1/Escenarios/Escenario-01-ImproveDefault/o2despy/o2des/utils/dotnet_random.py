"""
DotNetRandom — byte-for-byte re-implementation of C#'s System.Random(int Seed).

The .NET reference source for System.Random is preserved here verbatim (translated
to Python) so that the O2DES Python port produces stochastic output identical to
the C# / O2DESNet implementation. See:

    https://github.com/microsoft/referencesource/blob/main/mscorlib/system/random.cs

Algorithm: Knuth's subtractive lagged-Fibonacci generator from
"Numerical Recipes in C (2nd Ed.)", with constants:

    MBIG  = Int32.MaxValue = 2_147_483_647
    MSEED = 161_803_398

Index ranges
------------
- SeedArray: 56-element int array. Slot 0 is reserved/unused; slots 1..55 are live.
- inext:  next index to consume (advanced by InternalSample).
- inextp: partner index (== inext - 21 mod 56 in steady state).

The class is purely deterministic: identical seeds produce identical streams
across runs and across processes.
"""

from __future__ import annotations

import math
from typing import List


class DotNetRandom:
    """C# System.Random(int Seed) re-implementation in pure Python.

    Public methods mirror the C# API so call sites can be ported mechanically:

        next()        -> int    # [0, MBIG)
        next_double() -> float  # [0, 1.0)
        next_max(n)   -> int    # [0, n)

    The 32-bit signed arithmetic used by C# `int` is replicated by clamping
    every intermediate result through a private `_i32()` helper, since Python
    integers are arbitrary-precision and would otherwise drift the sequence.
    """

    MBIG: int = 2_147_483_647  # Int32.MaxValue
    MSEED: int = 161_803_398

    # Private class-level marker so the same Python int is reused everywhere
    # (avoids per-instance attribute lookup in the hot path of InternalSample).
    __slots__ = ("_seed_array", "_inext", "_inextp")

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, seed: int) -> None:
        """Initialise the PRNG state from a 32-bit seed.

        Mirrors `public Random(int Seed)` from .NET Framework reference source.
        The Int32.MinValue guard is required because C#'s `Math.Abs(Int32.MinValue)`
        would overflow; we substitute Int32.MaxValue in that case.
        """
        # SeedArray[0] is reserved/unused; allocate 56 slots.
        seed_array: List[int] = [0] * 56

        # int subtraction = (Seed == Int32.MinValue) ? Int32.MaxValue : Math.Abs(Seed)
        # Note: C# Math.Abs(Seed) is non-negative; ours is therefore a *non-negative*
        # Python int that we clamp to 32-bit signed range.
        if seed == -2_147_483_648:
            subtraction = 2_147_483_647
        else:
            subtraction = abs(seed)

        # mj = MSEED - subtraction  (C# signed int32 subtraction; may go negative)
        mj = self._i32(self.MSEED - subtraction)
        seed_array[55] = mj
        mk = 1

        # First loop: fill SeedArray[1..55] using the Knuth recurrence.
        for i in range(1, 55):
            ii = (21 * i) % 55
            seed_array[ii] = mk
            mk = self._i32(mj - mk)
            if mk < 0:
                mk += self.MBIG
            mj = seed_array[ii]

        # Second loop: warm up the state with 4 passes over slots 1..55.
        for _k in range(1, 5):
            for i in range(1, 56):
                seed_array[i] = self._i32(
                    seed_array[i] - seed_array[1 + (i + 30) % 55]
                )
                if seed_array[i] < 0:
                    seed_array[i] += self.MBIG

        # Initial cursor positions.
        inext = 0
        inextp = 21

        self._seed_array: List[int] = seed_array
        self._inext: int = inext
        self._inextp: int = inextp

    # ------------------------------------------------------------------
    # Public API (C# naming)
    # ------------------------------------------------------------------
    def next(self) -> int:
        """Return an int in [0, MBIG). Equivalent to C# Random.Next()."""
        return self._internal_sample()

    def next_double(self) -> float:
        """Return a float in [0, 1.0). Equivalent to C# Random.NextDouble()."""
        return self._sample()

    def next_max(self, max_value: int) -> int:
        """Return an int in [0, max_value). Equivalent to C# Random.Next(int).

        Routes through Sample() (not InternalSample()) to match C# behaviour
        precisely. `max_value` must be non-negative; matches the C# argument check.
        """
        if max_value < 0:
            raise ValueError("maxValue must be non-negative")
        return int(self._sample() * max_value)

    # ------------------------------------------------------------------
    # Aliases / convenience (numpy-style for ergonomic porting)
    # ------------------------------------------------------------------
    def random(self) -> float:
        """Alias of `next_double()`; matches `numpy.random.Generator.random`."""
        return self.next_double()

    def integers(self, low: int, high: int) -> int:  # noqa: A003 - mirrors numpy
        """Alias of `next_max(high - low) + low`; mirrors Generator.integers(low, high)."""
        if high <= low:
            raise ValueError("high must be strictly greater than low")
        return self.next_max(high - low) + low

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _sample(self) -> float:
        """C# `protected virtual double Sample() { return InternalSample() * (1.0/MBIG); }`

        Verified on .NET 10 (Windows) that `Sample()` returns exactly
        `InternalSample() * (1.0 / 2147483647)`, NOT `InternalSample() * 2^-31`.
        The runtime computes the reciprocal fresh per call, and `1.0 / 2147483647`
        evaluates to a value very slightly less than `2^-31` — both sides of the
        multiplication are then combined into the correctly-rounded product.
        Reproduced here verbatim.
        """
        return self._internal_sample() * (1.0 / self.MBIG)

    def _internal_sample(self) -> int:
        """C# `private int InternalSample()` — Knuth subtractive step.

        Advances `inext` and `inextp` (wrapping from 56 to 1, never 0), subtracts
        SeedArray[inextp] from SeedArray[inext], normalises the result, stores
        the new value, and returns it.
        """
        inext = self._inext
        inextp = self._inextp

        inext += 1
        if inext >= 56:
            inext = 1
        inextp += 1
        if inextp >= 56:
            inextp = 1

        retval = self._seed_array[inext] - self._seed_array[inextp]
        if retval == self.MBIG:
            retval -= 1
        if retval < 0:
            retval += self.MBIG

        self._seed_array[inext] = retval
        self._inext = inext
        self._inextp = inextp
        return retval

    @staticmethod
    def _i32(x: int) -> int:
        """Coerce a Python int to 32-bit signed range, matching C# `int` arithmetic.

        Every intermediate `int` in the C# algorithm is a signed 32-bit value, so
        e.g. `MSEED - subtraction` may legitimately be negative. We replicate the
        wraparound here: AND with 0xFFFFFFFF, then convert to signed.
        """
        x &= 0xFFFFFFFF
        if x & 0x80000000:
            x -= 0x100000000
        return x

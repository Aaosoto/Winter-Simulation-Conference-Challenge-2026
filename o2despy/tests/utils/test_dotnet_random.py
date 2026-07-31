"""
Unit tests for the DotNetRandom class (C# System.Random re-implementation).

These tests pin the byte-for-byte equivalence of the Python port to the
C# O2DESNet 3.7.1 implementation. Ground-truth values were captured from
`new Random(1)` on .NET 10 (Windows).

The `o2des.utils.__init__.py` package pulls in `pyjson5` and other optional
dependencies; we load `DotNetRandom` directly from the module file to keep
these tests runnable in any environment.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "o2des" / "utils" / "dotnet_random.py"
)


def _load_dotnet_random():
    """Load DotNetRandom directly from the .py file (bypassing o2des.utils init)."""
    spec = importlib.util.spec_from_file_location("_DotNetRandomModule", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DotNetRandom


DotNetRandom = _load_dotnet_random()


# ---------------------------------------------------------------------------
# 1.1 — First 3 `next()` for seed=1 must match C# exactly.
# ---------------------------------------------------------------------------
def test_seed_1_first_three_next():
    rs = DotNetRandom(1)
    assert rs.next() == 534_011_718
    assert rs.next() == 237_820_880
    assert rs.next() == 1_002_897_798


# ---------------------------------------------------------------------------
# 1.2 — First 3 `next_double()` for seed=1 must match C# within 1 ULP.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "call_index, expected",
    [
        (0, 0.24866858415709278),
        (1, 0.11074397718102856),
        (2, 0.46701067987224587),
    ],
)
def test_seed_1_next_double(call_index, expected):
    """Each call_index draws that many next_double()s from a fresh seed=1 RNG."""
    rs = DotNetRandom(1)
    for _ in range(call_index):
        rs.next_double()
    assert rs.next_double() == pytest.approx(expected, rel=1e-15, abs=1e-17)


# ---------------------------------------------------------------------------
# 1.3 — `next_max(100)` returns int in [0, 100); statistical sanity.
# ---------------------------------------------------------------------------
def test_next_max_in_range():
    rs = DotNetRandom(123)
    for _ in range(10_000):
        v = rs.next_max(100)
        assert 0 <= v < 100


def test_next_max_distribution_mean_around_half():
    rs = DotNetRandom(42)
    n = 100_000
    mean = sum(rs.next_max(100) for _ in range(n)) / n
    # Mean of Uniform[0, 100) is 49.5. Allow generous tolerance.
    assert 48.0 < mean < 51.0


# ---------------------------------------------------------------------------
# 1.4 — Int32.MinValue guard.
# ---------------------------------------------------------------------------
def test_int_min_value_guard_matches_int_max_value():
    """seed == Int32.MinValue must behave like seed == Int32.MaxValue."""
    rs_min = DotNetRandom(-2_147_483_648)
    rs_max = DotNetRandom(2_147_483_647)
    for _ in range(20):
        assert rs_min.next() == rs_max.next()


# ---------------------------------------------------------------------------
# 1.5 — `next_max(0) == 0`.
# ---------------------------------------------------------------------------
def test_next_max_zero():
    rs = DotNetRandom(7)
    assert rs.next_max(0) == 0


def test_next_max_negative_raises():
    rs = DotNetRandom(7)
    with pytest.raises(ValueError):
        rs.next_max(-1)


# ---------------------------------------------------------------------------
# 1.6 — First 1000 draws for seed=1 match a precomputed reference table.
# Captured by running `new Random(1)` in C# — see
# `SimulationChallenge2026_DotNet/tools/ExportRandomFixtures`.
# Here we hard-code a short prefix as a sanity check; the full table is
# generated separately and consumed by the end-to-end test.
# ---------------------------------------------------------------------------
def test_seed_1_next_first_five_match_csharp():
    expected = [534_011_718, 237_820_880, 1_002_897_798, 1_657_007_234, 1_412_011_072]
    rs = DotNetRandom(1)
    for exp in expected:
        assert rs.next() == exp


# ---------------------------------------------------------------------------
# 1.7 — Different seeds produce different streams.
# ---------------------------------------------------------------------------
def test_different_seeds_produce_different_streams():
    rs1 = DotNetRandom(1)
    rs2 = DotNetRandom(2)
    a = [rs1.next() for _ in range(10)]
    b = [rs2.next() for _ in range(10)]
    assert a != b


# ---------------------------------------------------------------------------
# 1.8 — Determinism: same seed → same long stream.
# ---------------------------------------------------------------------------
def test_same_seed_determinism():
    rs1 = DotNetRandom(2024)
    rs2 = DotNetRandom(2024)
    a = [rs1.next() for _ in range(1_000)]
    b = [rs2.next() for _ in range(1_000)]
    assert a == b


# ---------------------------------------------------------------------------
# 1.9 — Aliases behave consistently.
# ---------------------------------------------------------------------------
def test_random_alias_matches_next_double():
    rs = DotNetRandom(99)
    a = rs.next_double()
    rs2 = DotNetRandom(99)
    b = rs2.random()
    assert a == b


def test_integers_alias_matches_next_max():
    rs = DotNetRandom(99)
    a = rs.next_max(1_000_000_000)
    rs2 = DotNetRandom(99)
    b = rs2.integers(0, 1_000_000_000)
    assert a == b

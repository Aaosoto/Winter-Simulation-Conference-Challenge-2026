"""
Unit tests for the DotNetExponential and DotNetPoisson samplers.

These tests pin the byte-for-byte equivalence of the Python port to the
C# MathNet.Numerics 5.0.0 / O2DESNet 3.7.1 implementation. Ground-truth
values were captured from a small C# console program in
`SimulationChallenge2026_DotNet/tools/VerifyRandom/`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load(name: str, rel_path: str):
    base = Path(__file__).resolve().parents[2]  # o2despy/
    path = base / "o2des" / "utils" / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_drn = _load("_drn", "dotnet_random.py")
_ddn = _load("_ddn", "dotnet_distributions.py")
DotNetRandom = _drn.DotNetRandom
DotNetExponential = _ddn.DotNetExponential
DotNetPoisson = _ddn.DotNetPoisson
DotNetNegativeBinomial = _ddn.DotNetNegativeBinomial


# ---------------------------------------------------------------------------
# Exponential: byte-identical to MathNet.Exponential.Sample(rs, mean=2.0)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "call_index, expected",
    [
        (0, 0.6958171281943558),
        (1, 1.1002671268241309),
        (2, 0.3807015762346411),
        (3, 0.1296418278950766),
        (4, 0.20964088977307588),
    ],
)
def test_exponential_seed_1_matches_csharp(call_index, expected):
    rs = DotNetRandom(1)
    for _ in range(call_index):
        DotNetExponential.sample(rs, 2.0)
    val = DotNetExponential.sample(rs, 2.0)
    assert val == pytest.approx(expected, rel=1e-15, abs=1e-17)


def test_exponential_zero_input_rejected():
    rs = DotNetRandom(1)
    with pytest.raises(ValueError):
        DotNetExponential.sample(rs, 0.0)
    with pytest.raises(ValueError):
        DotNetExponential.sample(rs, -1.0)


# ---------------------------------------------------------------------------
# Poisson (Knuth branch, lambda < 30)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "call_index, expected",
    [
        (0, 10),
        (1, 11),
        (2, 10),
        (3, 14),
        (4, 8),
    ],
)
def test_poisson_seed_1_lambda_10_matches_csharp(call_index, expected):
    rs = DotNetRandom(1)
    for _ in range(call_index):
        DotNetPoisson.sample(rs, 10.0)
    assert DotNetPoisson.sample(rs, 10.0) == expected


# ---------------------------------------------------------------------------
# Poisson (Atkinson branch, lambda >= 30)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "call_index, expected",
    [
        (0, 46),
        (1, 53),
        (2, 41),
        (3, 36),
        (4, 46),
    ],
)
def test_poisson_seed_1_lambda_50_matches_csharp(call_index, expected):
    rs = DotNetRandom(1)
    for _ in range(call_index):
        DotNetPoisson.sample(rs, 50.0)
    assert DotNetPoisson.sample(rs, 50.0) == expected


# ---------------------------------------------------------------------------
# Sanity: distribution-level mean roughly matches lambda (Poisson) or mean (Exp).
# ---------------------------------------------------------------------------
def test_poisson_mean_within_tolerance():
    rs = DotNetRandom(2024)
    n = 50_000
    samples = [DotNetPoisson.sample(rs, 10.0) for _ in range(n)]
    mean = sum(samples) / n
    # Standard error ~ sqrt(10/n) ≈ 0.014; allow 5-sigma.
    assert abs(mean - 10.0) < 0.1


def test_exponential_mean_within_tolerance():
    rs = DotNetRandom(2024)
    n = 50_000
    samples = [DotNetExponential.sample(rs, 2.0) for _ in range(n)]
    mean = sum(samples) / n
    # MathNet 5.0.0 interprets the second arg as rate, so the mean of the
    # distribution is 1/2 = 0.5 (see comments in dotnet_distributions.py).
    assert abs(mean - 0.5) < 0.01


def test_negative_binomial_mean_and_overdispersion_within_tolerance():
    rs = DotNetRandom(2024)
    n = 50_000
    target_mean = 10.0
    dispersion = 2.0
    samples = [
        DotNetNegativeBinomial.sample(rs, target_mean, dispersion)
        for _ in range(n)
    ]
    mean = sum(samples) / n
    variance = sum((sample - mean) ** 2 for sample in samples) / n

    assert abs(mean - target_mean) < 0.2
    assert variance > target_mean * 4.0


def test_negative_binomial_invalid_inputs_rejected():
    rs = DotNetRandom(1)
    with pytest.raises(ValueError):
        DotNetNegativeBinomial.sample(rs, -1.0, 2.0)
    with pytest.raises(ValueError):
        DotNetNegativeBinomial.sample(rs, 1.0, 0.0)

"""
DotNet-compatible distribution samplers.

These are byte-for-byte re-implementations of the distribution samplers used
by O2DESNet (3.7.1) on top of `System.Random`. The source algorithms come from
Math.NET Numerics (https://github.com/mathnet/mathnet-numerics), MIT-licensed.

Two samplers are provided:

* `DotNetExponential.sample(rs, mean)` — inverse-CDF transform of a single
  uniform draw. Equivalent to
  `O2DESNet.Distributions.Exponential.Sample(rs, mean)`.
* `DotNetPoisson.sample(rs, lambda)` — dispatches on `lambda < 30.0`:
  - small λ: Knuth's product-of-uniforms (variable NextDouble() count)
  - large λ: Atkinson's rejection method PA (two NextDouble() per attempt)

`rs` must be a `DotNetRandom` (or any object with a `next_double()` method
matching C# `Random.NextDouble()` semantics — i.e. draws in `[0, 1)` via
the *Sample()* path, not the InternalSample path).
"""

from __future__ import annotations

import math
from typing import Protocol


class _SupportsNextDouble(Protocol):
    """Minimal protocol: a `next_double()` method that returns a float in [0, 1)."""
    def next_double(self) -> float: ...


# ---------------------------------------------------------------------------
# Exponential
# ---------------------------------------------------------------------------
class DotNetExponential:
    """Inverse-CDF exponential sampler matching C# O2DESNet behaviour.

    Equivalent to:
        double Sample(System.Random rs, double mean)
            => -Math.Log(rs.NextDouble()) * mean

    The first NextDouble() is consumed in the main expression; if it returns
    exactly 0.0 (probability 2^-31 — practically zero), the loop re-draws.
    The number of NextDouble() calls per sample is exactly 1 in the common case.
    """

    @staticmethod
    def sample(rs: _SupportsNextDouble, mean: float) -> float:
        """Sample one exponential variate with the given `mean`.

        Equivalent to:
            double Sample(System.Random rs, double mean)
                => -Math.Log(rs.NextDouble()) / mean

        Empirical finding (MathNet.Numerics 5.0.0 dll, .NET 10, Windows):
        MathNet's `Exponential.Sample(rnd, x)` actually computes
        `-Log(u) / x` (the inverse-CDF formula for rate-parameterised
        exponential), even though the parameter is named `rate` in
        signatures. O2DESNet (3.7.1) calls
        `Exponential.Sample(DefaultRS, MeanShipmentsPerDay)` directly —
        i.e. it passes `mean` to MathNet, which treats it as a rate. The
        resulting sample magnitude is therefore `1 / mean`, not `mean`.
        We reproduce this exactly to match the C# build byte-for-byte.

        The first NextDouble() is consumed in the main expression; if it
        returns exactly 0.0, the loop re-draws. Number of NextDouble() calls
        per sample is exactly 1 in the common case.
        """
        if mean <= 0:
            raise ValueError("mean must be positive for Exponential distribution")
        r = rs.next_double()
        while r == 0.0:
            r = rs.next_double()
        return -math.log(r) / mean


# ---------------------------------------------------------------------------
# Poisson
# ---------------------------------------------------------------------------
class DotNetPoisson:
    """Poisson sampler matching C# O2DESNet behaviour.

    Dispatches on `lambda < 30.0`:
      - small λ: Knuth's product-of-uniforms
      - large λ: Atkinson's rejection method PA
    """

    @staticmethod
    def sample(rs: _SupportsNextDouble, lambda_: float) -> int:
        """Sample one Poisson variate with mean `lambda_`.

        Verbatim from Math.NET Numerics `Poisson.SampleUnchecked`. Threshold
        for "small" vs "large" is `30.0` (matches the C# source).
        """
        if lambda_ < 30.0:
            return DotNetPoisson._do_sample_short(rs, lambda_)
        return DotNetPoisson._do_sample_large(rs, lambda_)

    @staticmethod
    def _do_sample_short(rs: _SupportsNextDouble, lambda_: float) -> int:
        """Knuth's product-of-uniforms algorithm.

        Equivalent to:
            var limit = Math.Exp(-lambda);
            var count = 0;
            for (var product = rs.NextDouble(); product >= limit;
                 product *= rs.NextDouble())
            {
                count++;
            }
            return count;
        """
        limit = math.exp(-lambda_)
        count = 0
        product = rs.next_double()
        while product >= limit:
            count += 1
            product *= rs.next_double()
        return count

    @staticmethod
    def _do_sample_large(rs: _SupportsNextDouble, lambda_: float) -> int:
        """Atkinson's rejection method PA (for λ >= 30).

        Verbatim from Math.NET Numerics `Poisson.DoSampleLarge`:
        """
        c = 0.767 - (3.36 / lambda_)
        beta = math.pi / math.sqrt(3.0 * lambda_)
        alpha = beta * lambda_
        # k = Math.Log(c) - lambda - Math.Log(beta)
        k = math.log(c) - lambda_ - math.log(beta)

        while True:
            u = rs.next_double()
            # x = (alpha - Math.Log((1.0 - u) / u)) / beta
            x = (alpha - math.log((1.0 - u) / u)) / beta
            n = int(math.floor(x + 0.5))
            if n < 0:
                continue
            v = rs.next_double()
            y = alpha - (beta * x)
            temp = 1.0 + math.exp(y)
            # lhs = y + Math.Log(v / (temp * temp))
            lhs = y + math.log(v / (temp * temp))
            # rhs = k + n * Math.Log(lambda) - SpecialFunctions.FactorialLn(n)
            # math.lgamma(n + 1) == ln(n!)  for integer n >= 0
            rhs = k + (n * math.log(lambda_)) - math.lgamma(n + 1)
            if lhs <= rhs:
                return n


# ---------------------------------------------------------------------------
# Negative Binomial
# ---------------------------------------------------------------------------
class DotNetNegativeBinomial:
    """Negative-binomial count sampler using a Gamma-Poisson mixture.

    The sampler is parameterised by mean and dispersion:

        E[X] = mean
        Var[X] = mean + mean^2 / dispersion

    Larger dispersion values approach Poisson behaviour. Smaller values create
    heavier tails, which is useful for shipment TEU sizes where occasional
    large shipments are more realistic than a pure Poisson process.
    """

    @staticmethod
    def sample(rs: _SupportsNextDouble, mean: float, dispersion: float) -> int:
        """Sample one negative-binomial variate."""
        if mean < 0:
            raise ValueError(
                "mean must be non-negative for Negative Binomial distribution"
            )
        if dispersion <= 0:
            raise ValueError(
                "dispersion must be positive for Negative Binomial distribution"
            )
        if mean == 0:
            return 0

        poisson_mean = DotNetNegativeBinomial._sample_gamma(
            rs,
            shape=dispersion,
            scale=mean / dispersion,
        )
        return DotNetPoisson.sample(rs, poisson_mean)

    @staticmethod
    def _sample_gamma(rs: _SupportsNextDouble, shape: float, scale: float) -> float:
        """Marsaglia-Tsang gamma sampler for positive shape and scale."""
        if shape <= 0 or scale <= 0:
            raise ValueError("shape and scale must be positive for Gamma distribution")

        if shape < 1.0:
            u = rs.next_double()
            while u == 0.0:
                u = rs.next_double()
            return DotNetNegativeBinomial._sample_gamma(
                rs,
                shape + 1.0,
                scale,
            ) * (u ** (1.0 / shape))

        d = shape - (1.0 / 3.0)
        c = 1.0 / math.sqrt(9.0 * d)

        while True:
            x = DotNetNegativeBinomial._sample_standard_normal(rs)
            v = 1.0 + c * x
            if v <= 0.0:
                continue
            v = v * v * v

            u = rs.next_double()
            if u < 1.0 - 0.0331 * (x ** 4):
                return scale * d * v
            if u == 0.0:
                continue
            if math.log(u) < 0.5 * x * x + d * (1.0 - v + math.log(v)):
                return scale * d * v

    @staticmethod
    def _sample_standard_normal(rs: _SupportsNextDouble) -> float:
        """Box-Muller standard normal sampler."""
        u1 = rs.next_double()
        while u1 == 0.0:
            u1 = rs.next_double()
        u2 = rs.next_double()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

from __future__ import annotations

from typing import overload

import numpy as np


class Beta:

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, a: float, b: float) -> float: ...

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, *, mean: float, cv: float) -> float: ...

    @classmethod
    def sample(
        cls,
        rs: np.random.Generator,
        a: float | None = None,
        b: float | None = None,
        *,
        mean: float | None = None,
        cv: float | None = None,
    ) -> float:
        if a is not None and b is not None:  # shape parameters
            if a <= 0 or b <= 0:
                raise ValueError("Shape parameters a and b must be positive for Beta distribution")

            return rs.beta(a, b)

        elif mean is not None and cv is not None:  # mean and coefficient of variation
            if mean <= 0 or mean >= 1:
                raise ValueError("Mean must be in (0, 1) for Beta distribution")
            if cv < 0:
                raise ValueError("Coefficient of variation must be non-negative for Beta distribution")

            if cv == 0:
                return mean

            stddev = cv * mean
            variance = stddev ** 2

            if variance >= mean * (1 - mean):
                raise ValueError("Variance too large for given mean in Beta distribution")

            alpha = mean * (mean * (1 - mean) / variance - 1)
            beta = (1 - mean) * (mean * (1 - mean) / variance - 1)

            if alpha <= 0 or beta <= 0:
                raise ValueError("Calculated shape parameters alpha and beta must be positive for Beta distribution")

            return rs.beta(alpha, beta)

        else:
            raise ValueError("Must provide either (a, b) or (mean, cv)")


class Exponential:

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, lambda_: float) -> float: ...

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, *, beta: float) -> float: ...

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, *, mean: float) -> float: ...

    @classmethod
    def sample(
        cls,
        rs: np.random.Generator,
        lambda_: float | None = None,
        *,
        beta: float | None = None,
        mean: float | None = None,
    ) -> float:
        if lambda_ is not None:  # lambda: rate parameter
            if lambda_ <= 0:
                raise ValueError("Lambda must be positive for Exponential distribution")
            return rs.exponential(1 / lambda_)

        elif beta is not None:  # beta: scale parameter
            if beta <= 0:
                raise ValueError("Beta must be positive for Exponential distribution")
            return rs.exponential(beta)

        elif mean is not None:  # mean
            if mean <= 0:
                raise ValueError("Mean must be positive for Exponential distribution")
            return rs.exponential(mean)

        else:
            raise ValueError("Must provide either _lambda or _mean")


class Gamma:

    @classmethod
    def sample(cls, rs: np.random.Generator, mean: float, cv: float) -> float:
        if mean == 0 or cv == 0:
            return mean

        k = 1 / cv**2  # shape
        lambd = k / mean  # rate
        theta = mean / k  # scale
        return rs.gamma(k, theta)


class Geometric:

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, p: float) -> int: ...

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, *, mean: float) -> int: ...

    @classmethod
    def sample(
        cls,
        rs: np.random.Generator,
        p: float | None = None,
        *,
        mean: float | None = None,
    ) -> int:
        if p is not None:  # probability of success
            if p <= 0 or p > 1:
                raise ValueError("Probability p must be in (0, 1] for Geometric distribution")

            return rs.geometric(p)

        elif mean is not None:  # mean
            if mean <= 0:
                raise ValueError("Mean must be positive for Geometric distribution")

            prob = 1 / mean
            return rs.geometric(prob)

        else:
            raise ValueError("Must provide either p or _mean")


class Normal:

    @classmethod
    def sample(cls, rs: np.random.Generator, mean: float, cv: float) -> float:
        if cv < 0:
            raise ValueError("Coefficient of variation must be non-negative for Normal distribution")

        if cv == 0:
            return mean

        stddev = cv * abs(mean)
        return rs.normal(mean, stddev)


class Poisson:

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, lambda_: float) -> int: ...

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, *, mean: float) -> int: ...

    @classmethod
    def sample(
        cls,
        rs: np.random.Generator,
        lambda_: float | None = None,
        *,
        mean: float | None = None,
    ) -> int:
        if lambda_ is not None:  # lambda: rate parameter
            if lambda_ < 0:
                raise ValueError("Lambda must be non-negative for Poisson distribution")

            return rs.poisson(lambda_)

        elif mean is not None:  # mean
            if mean < 0:
                raise ValueError("Mean must be non-negative for Poisson distribution")

            return rs.poisson(mean)

        else:
            raise ValueError("Must provide either _lambda or _mean")


class Triangular:

    @classmethod
    def sample(
        cls,
        rs: np.random.Generator,
        lowerbound: float,
        mode: float,
        upperbound: float,
    ) -> float:
        if not (lowerbound <= mode <= upperbound):
            raise ValueError("Must satisfy: lowerbound <= mode <= upperbound")

        return rs.triangular(lowerbound, mode, upperbound)


class Uniform:

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, lowerbound: float, upperbound: float) -> float: ...

    @overload
    @classmethod
    def sample(cls, rs: np.random.Generator, *, mean: float, cv: float) -> float: ...

    @classmethod
    def sample(
        cls,
        rs: np.random.Generator,
        lowerbound: float | None = None,
        upperbound: float | None = None,
        *,
        mean: float | None = None,
        cv: float | None = None,
    ) -> float:
        if lowerbound is not None and upperbound is not None:  # bounds
            return rs.uniform(lowerbound, upperbound)

        elif mean is not None and cv is not None:  # mean and coefficient of variation
            if cv < 0:
                raise ValueError("Coefficient of variation must be non-negative for Uniform distribution")

            if cv == 0:
                return mean

            stddev = cv * abs(mean)
            range_width = stddev * np.sqrt(12)
            lower = mean - range_width / 2
            upper = mean + range_width / 2

            return rs.uniform(lower, upper)

        else:
            raise ValueError("Must provide either (lowerbound, upperbound) or (_mean, _cv)")

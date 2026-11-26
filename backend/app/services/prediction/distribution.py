"""Turn the model's bucket probabilities into a range and a chance of going up.

The model sorts the coming return (in volatility units) into one of a
fixed set of buckets and gives a probability for each. Reading those as a
piecewise-linear distribution gives any percentile, and because 0 is one
of the bucket edges, the chance of going up is an exact sum of buckets.
"""

from dataclasses import dataclass

import numpy as np

# Percentiles of the training targets that become bucket edges.
EDGE_PERCENTILES = (2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98)
# The outer buckets are closed at these percentiles of the training targets.
OUTER_PERCENTILES = (0.5, 99.5)

LOW_Q, MID_Q, HIGH_Q = 0.1, 0.5, 0.9


@dataclass(frozen=True)
class Buckets:
    edges: np.ndarray  # inner edges, ascending, includes 0
    low: float  # lower bound of the first bucket
    high: float  # upper bound of the last bucket

    @property
    def count(self) -> int:
        return len(self.edges) + 1

    @property
    def points(self) -> np.ndarray:
        return np.concatenate([[self.low], self.edges, [self.high]])

    @classmethod
    def fit(cls, targets: np.ndarray) -> "Buckets":
        edges = np.percentile(targets, EDGE_PERCENTILES)
        edges = np.unique(np.round(np.append(edges, 0.0), 6))
        low, high = np.percentile(targets, OUTER_PERCENTILES)
        return cls(
            edges=edges,
            low=float(min(low, edges[0] - 1e-3)),
            high=float(max(high, edges[-1] + 1e-3)),
        )

    def label(self, targets: np.ndarray) -> np.ndarray:
        """Bucket index of each target (edges belong to the bucket above)."""
        return np.searchsorted(self.edges, targets, side="right")


def full_probabilities(probs: np.ndarray, classes: np.ndarray, count: int) -> np.ndarray:
    """Columns for every bucket, even ones a training fold never saw."""
    full = np.zeros((probs.shape[0], count))
    full[:, classes] = probs
    return full


def quantiles(probs: np.ndarray, buckets: Buckets, levels: tuple[float, ...]) -> np.ndarray:
    """Percentiles (rows x levels) of each row's bucket distribution."""
    points = buckets.points
    cdf = np.concatenate([np.zeros((probs.shape[0], 1)), np.cumsum(probs, axis=1)], axis=1)
    cdf[:, -1] = 1.0
    rows = np.arange(probs.shape[0])
    out = np.empty((probs.shape[0], len(levels)))
    for k, level in enumerate(levels):
        # First CDF point at or above the level; the bucket ending there
        # has probability > 0, so empty buckets are skipped.
        j = np.clip((cdf < level).sum(axis=1), 1, len(points) - 1)
        lo, hi = cdf[rows, j - 1], cdf[rows, j]
        frac = np.where(hi > lo, (level - lo) / np.where(hi > lo, hi - lo, 1), 0.0)
        out[:, k] = points[j - 1] + frac * (points[j] - points[j - 1])
    return out


def chance_up(probs: np.ndarray, buckets: Buckets) -> np.ndarray:
    above_zero = buckets.points[:-1] >= 0
    return probs[:, above_zero].sum(axis=1)

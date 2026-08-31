import random

import numpy as np

from banknifty_profiler.new_divergence.statistics import OrderStatisticMultiset


def test_online_statistics_equal_exact_batch_definitions() -> None:
    rng = random.Random(94731)
    values = []
    tree = OrderStatisticMultiset()
    for _ in range(500):
        value = rng.choice((rng.uniform(-50, 75), 0.0, 2.5, -1.0))
        values.append(value)
        tree.add(value)
        expected_median = float(np.median(values))
        assert tree.median() == expected_median
        assert tree.mad(expected_median) == float(
            np.median(np.abs(np.asarray(values) - expected_median))
        )
        assert tree.percentile_le(value) == sum(item <= value for item in values) / len(values)

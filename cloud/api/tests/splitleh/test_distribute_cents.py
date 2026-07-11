import pytest

from splitleh.calculate_split import distribute_in_cents


@pytest.mark.parametrize(
    "total,weights,expected",
    [
        (300, [1, 1, 1], [100, 100, 100]),
        (100, [1, 1, 1], [34, 33, 33]),
        (300, [2, 1], [200, 100]),
        (10, [3, 1], [8, 2]),
        (100, [0, 0], [50, 50]),
        (101, [0, 0], [51, 50]),
        (500, [1], [500]),
        (-100, [1, 1], [-50, -50]),
        (-99, [1, 1, 1], [-33, -33, -33]),
    ],
    ids=[
        "even_divisible",
        "even_remainder",
        "proportional_2_1",
        "proportional_odd_cent",
        "zero_weights_equal",
        "zero_weights_odd",
        "single_recipient",
        "negative_even",
        "negative_three_way",
    ],
)
def test_distribute_in_cents(total, weights, expected):
    assert distribute_in_cents(total, weights) == expected


@pytest.mark.parametrize("total", [1, 7, 99, 1000, 10001])
def test_distribute_in_cents_sums_to_total(total):
    weights = [3, 2, 1, 4]
    result = distribute_in_cents(total, weights)
    assert sum(result) == total
    assert len(result) == len(weights)

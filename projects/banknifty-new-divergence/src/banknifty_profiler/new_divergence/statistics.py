"""Deterministic online order statistics used by the causal detector.

The frozen detector uses an expanding percentile, median, and median absolute
deviation (MAD).  Recomputing those values from every observation is quadratic.
This module keeps the same exact definitions with an order-statistic treap, so
replay and live processing have the same incremental implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct


def _priority(value: float) -> int:
    """Return a stable pseudo-random priority for a finite IEEE-754 value."""

    raw = struct.pack("!d", value)
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big")


@dataclass
class _Node:
    key: float
    priority: int
    count: int = 1
    size: int = 1
    left: "_Node | None" = None
    right: "_Node | None" = None


def _size(node: _Node | None) -> int:
    return 0 if node is None else node.size


def _refresh(node: _Node) -> None:
    node.size = node.count + _size(node.left) + _size(node.right)


def _rotate_left(node: _Node) -> _Node:
    child = node.right
    assert child is not None
    node.right = child.left
    child.left = node
    _refresh(node)
    _refresh(child)
    return child


def _rotate_right(node: _Node) -> _Node:
    child = node.left
    assert child is not None
    node.left = child.right
    child.right = node
    _refresh(node)
    _refresh(child)
    return child


def _insert(node: _Node | None, value: float) -> _Node:
    if node is None:
        return _Node(value, _priority(value))
    if value == node.key:
        node.count += 1
    elif value < node.key:
        node.left = _insert(node.left, value)
        if node.left is not None and node.left.priority < node.priority:
            node = _rotate_right(node)
    else:
        node.right = _insert(node.right, value)
        if node.right is not None and node.right.priority < node.priority:
            node = _rotate_left(node)
    _refresh(node)
    return node


class OrderStatisticMultiset:
    """Finite-float multiset with exact rank, median, and MAD queries."""

    def __init__(self) -> None:
        self._root: _Node | None = None

    def __len__(self) -> int:
        return _size(self._root)

    def add(self, value: float) -> None:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("order statistics accept only finite values")
        self._root = _insert(self._root, number)

    def rank_le(self, value: float) -> int:
        node = self._root
        result = 0
        while node is not None:
            if value < node.key:
                node = node.left
            else:
                result += _size(node.left) + node.count
                node = node.right
        return result

    def kth(self, index: int) -> float:
        if index < 0 or index >= len(self):
            raise IndexError(index)
        node = self._root
        while node is not None:
            left = _size(node.left)
            if index < left:
                node = node.left
            elif index < left + node.count:
                return node.key
            else:
                index -= left + node.count
                node = node.right
        raise RuntimeError("corrupt order-statistic tree")

    def median(self) -> float:
        count = len(self)
        if count == 0:
            raise ValueError("median of empty multiset")
        middle = count // 2
        if count % 2:
            return self.kth(middle)
        return (self.kth(middle - 1) + self.kth(middle)) / 2.0

    def percentile_le(self, value: float) -> float:
        if not self:
            raise ValueError("percentile of empty multiset")
        return self.rank_le(float(value)) / len(self)

    def _deviation_at(self, median: float, side: str, index: int, split: int) -> float:
        if side == "left":
            return median - self.kth(split - 1 - index)
        return self.kth(split + index) - median

    def _kth_absolute_deviation(self, median: float, index: int) -> float:
        """Select from two sorted virtual arrays of distances around median."""

        split = self.rank_le(median)
        left_count = split
        right_count = len(self) - split

        # Binary-partition selection of the first index+1 values in A and B.
        take = index + 1
        low = max(0, take - right_count)
        high = min(take, left_count)
        infinity = float("inf")
        while low <= high:
            from_left = (low + high) // 2
            from_right = take - from_left
            left_before = (
                -infinity
                if from_left == 0
                else self._deviation_at(median, "left", from_left - 1, split)
            )
            left_after = (
                infinity
                if from_left == left_count
                else self._deviation_at(median, "left", from_left, split)
            )
            right_before = (
                -infinity
                if from_right == 0
                else self._deviation_at(median, "right", from_right - 1, split)
            )
            right_after = (
                infinity
                if from_right == right_count
                else self._deviation_at(median, "right", from_right, split)
            )
            if left_before <= right_after and right_before <= left_after:
                return max(left_before, right_before)
            if left_before > right_after:
                high = from_left - 1
            else:
                low = from_left + 1
        raise RuntimeError("failed to select absolute deviation")

    def mad(self, median: float | None = None) -> float:
        count = len(self)
        if count == 0:
            raise ValueError("MAD of empty multiset")
        centre = self.median() if median is None else float(median)
        middle = count // 2
        if count % 2:
            return self._kth_absolute_deviation(centre, middle)
        return (
            self._kth_absolute_deviation(centre, middle - 1)
            + self._kth_absolute_deviation(centre, middle)
        ) / 2.0

    def __bool__(self) -> bool:
        return self._root is not None

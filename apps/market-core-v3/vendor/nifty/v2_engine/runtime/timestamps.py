"""Strict canonical timestamp parsing for analytical availability clocks.

Valid ISO-8601 values may use exact seconds or any supported fractional-second
precision and must carry an explicit UTC offset (including ``Z``).  Values are
preserved as instants and normalized to Asia/Kolkata.  Missing, malformed and
timezone-naive causal timestamps are refused rather than coerced to NaT.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Iterable

import pandas as pd

CANONICAL_TIMEZONE = "Asia/Kolkata"


def _missing(value: object) -> bool:
    if value is None or value == "":
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def parse_timestamp(value: object, *, field_name: str = "timestamp") -> pd.Timestamp:
    """Parse one required timezone-aware timestamp without rounding."""
    if _missing(value):
        raise ValueError(f"missing required timezone-aware {field_name}")
    if isinstance(value, pd.Timestamp):
        result = value
    elif isinstance(value, datetime):
        result = pd.Timestamp(value)
    elif isinstance(value, str):
        text = value.strip().replace(" ", "T")
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            result = pd.Timestamp(datetime.fromisoformat(text))
        except ValueError as error:
            raise ValueError(f"malformed {field_name}: {value!r}") from error
    else:
        raise ValueError(f"unsupported {field_name} type: {type(value).__name__}")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"timezone-naive {field_name}: {value!r}")
    return result.tz_convert(CANONICAL_TIMEZONE)


def parse_timestamp_series(values: Iterable[object], *, field_name: str,
                           allow_missing: bool = False) -> pd.Series:
    """Parse mixed valid ISO formats independently and return one aware dtype."""
    index = getattr(values, "index", None)
    prepared = []
    for value in values:
        if allow_missing and _missing(value):
            prepared.append(None)
        elif _missing(value):
            raise ValueError(f"missing required timezone-aware {field_name}")
        elif isinstance(value, str):
            text=value.strip().replace(" ","T")
            if not re.search(r"(?:[Zz]|[+-]\d{2}:\d{2})$",text):
                raise ValueError(f"timezone-naive {field_name}: {value!r}")
            prepared.append(text)
        elif isinstance(value,(datetime,pd.Timestamp)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"timezone-naive {field_name}: {value!r}")
            prepared.append(value)
        else:
            raise ValueError(f"unsupported {field_name} type: {type(value).__name__}")
    try:
        result=pd.Series(pd.to_datetime(prepared,format="mixed",errors="raise",utc=True),index=index).dt.tz_convert(CANONICAL_TIMEZONE)
    except (TypeError,ValueError) as error:
        raise ValueError(f"malformed {field_name}") from error
    if not allow_missing and result.isna().any():
        raise ValueError(f"valid {field_name} was silently converted to NaT")
    return result

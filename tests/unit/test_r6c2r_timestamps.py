from __future__ import annotations

import pandas as pd
import pytest

from banknifty_profiler.divergence.detector import causal_basis
from banknifty_profiler.runtime.timestamps import parse_timestamp, parse_timestamp_series


def values(items):
    return [x.isoformat() for x in parse_timestamp_series(pd.Series(items), field_name="test timestamp")]


def test_exact_second_then_fractional():
    assert values(["2026-08-18T09:47:37+05:30", "2026-08-18T09:47:37.277326+05:30"]) == ["2026-08-18T09:47:37+05:30", "2026-08-18T09:47:37.277326+05:30"]


def test_fractional_then_exact_second():
    assert values(["2026-08-18T09:47:36.681982+05:30", "2026-08-18T09:47:37+05:30"])[1] == "2026-08-18T09:47:37+05:30"


def test_mixed_fractional_precision():
    result=values(["2026-08-18T09:47:36.1+05:30","2026-08-18T09:47:36.123+05:30","2026-08-18T09:47:36.123456+05:30","2026-08-18T09:47:37+05:30"])
    assert len(result)==4 and all("+05:30" in x for x in result)


def test_positive_offset_and_z_normalize_to_ist():
    assert parse_timestamp("2026-08-18T04:17:37Z").isoformat()=="2026-08-18T09:47:37+05:30"
    assert parse_timestamp("2026-08-18T09:47:37+05:30").isoformat()=="2026-08-18T09:47:37+05:30"


@pytest.mark.parametrize("invalid", ["2026-08-18T09:47:37", "not-a-time", "", None])
def test_invalid_required_timestamp_refused(invalid):
    with pytest.raises(ValueError):parse_timestamp(invalid)


def test_exact_disputed_receipt_preserved():
    assert parse_timestamp("2026-08-18T09:47:37+05:30").isoformat()=="2026-08-18T09:47:37+05:30"


def frame(index_times, future_time):
    rows=[]
    for ordinal,(timestamp,price) in enumerate(index_times):rows.append({"symbol":"INDEX","receipt_timestamp":parse_timestamp(timestamp),"last_price":price,"source_file":"fixture","source_row":ordinal})
    rows.append({"symbol":"FUTURES","receipt_timestamp":parse_timestamp(future_time),"last_price":57450.2,"source_file":"fixture","source_row":99})
    return pd.DataFrame(rows)


def test_latest_backward_selection_at_277_326ms():
    data=frame([("2026-08-18T09:47:36.681982+05:30",57334.30),("2026-08-18T09:47:37+05:30",57333.65)],"2026-08-18T09:47:37.277326+05:30")
    row=causal_basis(data,"2026-08-18","INDEX","FUTURES",2000)[0]
    assert row["index_receipt_timestamp"]=="2026-08-18T09:47:37+05:30"
    assert row["index_price"]==57333.65 and row["absolute_receipt_difference_ms"]==pytest.approx(277.326)


@pytest.mark.parametrize("age,valid", [(0,"VALID"),(2000,"VALID"),(2001,"UNMATCHED_TOLERANCE_EXCEEDED")])
def test_causal_tolerance_boundaries(age,valid):
    future=parse_timestamp("2026-08-18T09:47:37.277326+05:30");prior=future-pd.Timedelta(milliseconds=age)
    row=causal_basis(frame([(prior.isoformat(),57333.65)],future.isoformat()),"2026-08-18","INDEX","FUTURES",2000)[0]
    assert row["validity_status"]==valid


def test_future_index_receipt_never_selected():
    data=frame([("2026-08-18T09:47:37+05:30",57333.65),("2026-08-18T09:47:37.300000+05:30",99999)],"2026-08-18T09:47:37.277326+05:30")
    row=causal_basis(data,"2026-08-18","INDEX","FUTURES",2000)[0]
    assert row["index_price"]==57333.65


def test_equal_timestamp_secondary_order_is_deterministic():
    data=frame([("2026-08-18T09:47:37+05:30",57333.60),("2026-08-18T09:47:37+05:30",57333.65)],"2026-08-18T09:47:37.277326+05:30")
    assert causal_basis(data,"2026-08-18","INDEX","FUTURES",2000)[0]["index_price"]==57333.65


def test_stream_batch_timestamp_parsing_identity():
    source=pd.Series(["2026-08-18T09:47:36.681982+05:30","2026-08-18T09:47:37+05:30","2026-08-18T09:47:37.277326+05:30"])
    stream=parse_timestamp_series(source,field_name="stream")
    batch=parse_timestamp_series(source.copy(),field_name="batch")
    assert stream.to_list()==batch.to_list()

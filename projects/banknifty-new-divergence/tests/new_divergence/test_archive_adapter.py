from datetime import date
import io
import json
import tarfile

import pytest

from banknifty_profiler.new_divergence.collector_archive import (
    ActiveContractUnavailable,
    CollectorArchiveAdapter,
)
from banknifty_profiler.new_divergence.contracts import EventKind


def _add(archive, name, rows):
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    member = tarfile.TarInfo(name)
    member.size = len(raw)
    archive.addfile(member, io.BytesIO(raw))


def _raw(receipt, symbol, price):
    return {
        "received_at": receipt,
        "event_time": receipt,
        "timestamp_source": "exchange",
        "message": {"symbol": symbol, "ltp": price},
    }


def test_tar_members_are_streamed_and_externally_receipt_sorted(tmp_path) -> None:
    path = tmp_path / "collector.tar.gz"
    startup = {
        "started_at": "2031-04-07T09:01:00+05:30",
        "future_oi_symbols": ["NSE:BANKNIFTY31APRFUT"],
        "base_quote_symbols": ["NSE:NIFTYBANK-INDEX"],
    }
    with tarfile.open(path, "w:gz") as archive:
        raw = json.dumps(startup).encode()
        member = tarfile.TarInfo("feed/metadata/startup_dynamic.json")
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
        _add(archive, "feed/raw/2031-04-07/events_10.jsonl", [
            _raw("2031-04-07T10:00:00+05:30", "NSE:NIFTYBANK-INDEX", 100),
            _raw("2031-04-07T10:00:00.200000+05:30", "NSE:BANKNIFTY31APRFUT", 107),
        ])
        _add(archive, "feed/raw/2031-04-07/events_09.jsonl", [
            _raw("2031-04-07T09:59:00+05:30", "NSE:NIFTYBANK-INDEX", 101),
            _raw("2031-04-07T09:59:00.200000+05:30", "NSE:BANKNIFTY31APRFUT", 106),
            _raw("2031-04-07T09:59:01+05:30", "NSE:IGNORED-EQ", 1),
        ])
    adapter = CollectorArchiveAdapter(path, date(2031, 4, 7), include_auxiliary=False, chunk_size=2)
    events = list(adapter.stream())
    assert [event.kind for event in events] == [
        EventKind.INDEX_TICK, EventKind.FUTURES_TICK,
        EventKind.INDEX_TICK, EventKind.FUTURES_TICK,
    ]
    assert [event.receipt_timestamp for event in events] == sorted(event.receipt_timestamp for event in events)
    assert adapter.selected_futures_symbol == "NSE:BANKNIFTY31APRFUT"
    assert adapter.stats["raw_payload_extracted"] is False


def test_malformed_selected_jsonl_fails_closed(tmp_path) -> None:
    path = tmp_path / "malformed.tar.gz"
    raw = b"{not-json}\n"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("feed/raw/2031-04-07/events_09.jsonl")
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
    adapter = CollectorArchiveAdapter(path, date(2031, 4, 7), include_auxiliary=False)
    with pytest.raises(ValueError, match="1 invalid selected JSONL rows"):
        list(adapter.stream())


def test_missing_active_contract_metadata_fails_closed(tmp_path) -> None:
    path = tmp_path / "no-metadata.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        _add(archive, "feed/raw/2031-04-07/events_09.jsonl", [
            _raw("2031-04-07T09:45:00+05:30", "NSE:BANKNIFTY31APRFUT", 107),
        ])
    adapter = CollectorArchiveAdapter(path, date(2031, 4, 7), include_auxiliary=False)
    with pytest.raises(ActiveContractUnavailable, match="startup metadata"):
        list(adapter.stream())


def test_non_price_target_update_is_counted_not_misclassified(tmp_path) -> None:
    path = tmp_path / "non-price.tar.gz"
    startup = {
        "started_at": "2031-04-07T09:01:00+05:30",
        "future_oi_symbols": ["NSE:BANKNIFTY31APRFUT"],
        "base_quote_symbols": ["NSE:NIFTYBANK-INDEX"],
    }
    with tarfile.open(path, "w:gz") as archive:
        raw = json.dumps(startup).encode()
        member = tarfile.TarInfo("feed/metadata/startup_dynamic.json")
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
        _add(archive, "feed/raw/2031-04-07/events_09.jsonl", [
            _raw("2031-04-07T09:45:00+05:30", "NSE:BANKNIFTY31APRFUT", 0),
        ])
    adapter = CollectorArchiveAdapter(path, date(2031, 4, 7), include_auxiliary=False)
    assert list(adapter.stream()) == []
    assert adapter.stats["invalid_lines"] == 0
    assert adapter.stats["excluded_rows"] == {"FUTURES_TICK_NON_PRICE_UPDATE": 1}


def test_option_chain_retains_compact_selected_expiry_strike_oi(tmp_path) -> None:
    path = tmp_path / "option-chain.tar.gz"
    option_chain = {
        "source": "option_chain",
        "received_at": "2031-04-07T09:45:01+05:30",
        "request_time": "2031-04-07T09:45:00.900000+05:30",
        "input_symbol": "NSE:NIFTYBANK-INDEX",
        "response": {
            "data": {
                "expiryData": [{"date": "10-04-2031", "expiry": "1933486200"}],
                "optionsChain": [
                    {
                        "symbol": "NSE:BANKNIFTY10APR3110000CE",
                        "option_type": "CE",
                        "strike_price": 10_000,
                        "oi": 1_000,
                        "oich": 10,
                        "volume": 500,
                        "ltp": 125.5,
                    },
                    {
                        "symbol": "NSE:BANKNIFTY10APR3110000PE",
                        "option_type": "PE",
                        "strike_price": 10_000,
                        "oi": 1_200,
                        "oich": 20,
                        "volume": 600,
                        "ltp": 118.0,
                    },
                ],
            }
        },
    }
    with tarfile.open(path, "w:gz") as archive:
        _add(archive, "feed/oi/2031-04-07/oi_09.jsonl", [option_chain])

    events = list(CollectorArchiveAdapter(path, date(2031, 4, 7)).stream())
    assert len(events) == 1
    option = events[0]
    assert option.kind == EventKind.OPTION_PRESSURE
    assert option.values["selected_expiry"] == "10-04-2031"
    assert option.values["score"] == pytest.approx(1 / 3)
    assert option.values["strike_oi"] == [
        {
            "expiry": "10-04-2031",
            "option_type": "CE",
            "strike": 10_000.0,
            "oi": 1_000.0,
            "price": 125.5,
            "volume": 500.0,
            "symbol": "NSE:BANKNIFTY10APR3110000CE",
        },
        {
            "expiry": "10-04-2031",
            "option_type": "PE",
            "strike": 10_000.0,
            "oi": 1_200.0,
            "price": 118.0,
            "volume": 600.0,
            "symbol": "NSE:BANKNIFTY10APR3110000PE",
        },
    ]

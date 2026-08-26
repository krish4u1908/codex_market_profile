"""Typed, lossless analytical observation envelope for the live shadow."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields, replace
from typing import Any

from banknifty_profiler.runtime.timestamps import parse_timestamp


Number = int | float
_INSTRUMENT_ORDER = {
    "INDEX": 0,
    "FUTURES": 1,
    "FUTURES_OI": 2,
    "CE": 3,
    "PE": 4,
}


@dataclass(frozen=True, slots=True)
class TypedObservation(Mapping[str, Any]):
    """One causally available analytical observation.

    It implements ``Mapping`` to retain compatibility with the pre-R6E1R
    dictionary interface while giving internal consumers a fixed typed shape.
    ``canonical_payload`` is an allow-listed analytical projection, never the
    arbitrary collector response.
    """

    observation_id: str
    event_id: str
    session_date: str
    instrument_class: str
    canonical_symbol: str | None
    source_symbol: str
    receipt_timestamp: str
    event_timestamp: str | None
    exchange_timestamp: str | None
    price: Number | None
    cumulative_volume: Number | None
    open_interest: Number | None
    previous_open_interest: Number | None
    open_interest_change: Number | None
    oi: Number | None
    previous_oi: Number | None
    delta_oi: Number | None
    strike: Number | None
    option_type: str | None
    expiry: str | None
    expiry_date: str | None
    underlying_price: Number | None
    forward_price: Number | None
    source_file: str
    source_byte_offset: int
    source_row_number: int
    source_row: int
    raw_record_id: str
    availability_status: str
    freshness_status: str
    out_of_order: bool
    canonical_payload: dict[str, Any]
    effective_timestamp: str
    publication_timestamp: str
    source_receipt_identifiers: dict[str, Any]
    engine_hash: str
    configuration_hash: str
    raw_run_id: str
    status: str
    reason: str
    classification_reason: str

    def __getitem__(self, key: str) -> Any:
        if key not in self.keys():
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(fields(self))

    @classmethod
    def keys(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.keys()}

    def marked_out_of_order(self) -> "TypedObservation":
        return replace(
            self,
            out_of_order=True,
            availability_status="OUT_OF_ORDER_AVAILABLE",
        )

    def causal_sort_key(self) -> tuple[Any, ...]:
        """Frozen canonical receipt ordering and deterministic secondary keys."""
        return (
            parse_timestamp(self.receipt_timestamp, field_name="observation receipt timestamp"),
            _INSTRUMENT_ORDER.get(self.instrument_class, 99),
            self.canonical_symbol or self.source_symbol,
            self.source_file,
            self.source_byte_offset,
            self.source_row_number,
            self.observation_id,
        )

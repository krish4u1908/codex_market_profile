"""Repository-owned BankNifty symbol classification.

The Index is deliberately recognised by exact identity.  Derivatives are
accepted only when they match the complete canonical NSE BankNifty contract
grammar; arbitrary suffix matching is never used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
import re
from collections.abc import Iterable, Mapping
from zoneinfo import ZoneInfo


CANONICAL_INDEX_SYMBOL = "NSE:NIFTYBANK-INDEX"
CANONICAL_FUTURES_SYMBOL = "NSE:BANKNIFTY26AUGFUT"
_MONTH_NUMBER = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_FUTURES = re.compile(
    r"^NSE:BANKNIFTY(?P<year>\d{2})(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)FUT$"
)
_OPTION = re.compile(
    r"^NSE:BANKNIFTY(?P<year>\d{2})(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
    r"(?P<strike>\d+(?:\.\d+)?)(?P<option_type>CE|PE)$"
)
_IST = ZoneInfo("Asia/Kolkata")


class InstrumentClass(StrEnum):
    INDEX = "INDEX"
    FUTURES = "FUTURES"
    FUTURES_OI = "FUTURES_OI"
    CE = "CE"
    PE = "PE"
    OPTION_OI = "OPTION_OI"
    UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"


@dataclass(frozen=True, slots=True)
class SymbolClassification:
    instrument_class: InstrumentClass
    canonical_symbol: str | None
    source_symbol: str
    expiry: str | None = None
    strike: int | float | None = None
    option_type: str | None = None
    reason: str = "CANONICAL_SYMBOL_MATCH"

    @property
    def known(self) -> bool:
        return self.instrument_class is not InstrumentClass.UNKNOWN_SYMBOL


def normalize_expiry(value: object) -> str | None:
    """Return verified expiry metadata as an ISO date without guessing a day."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(_IST)
        return parsed.date().isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return None
        return datetime.fromtimestamp(float(value), tz=_IST).date().isoformat()
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        try:
            return datetime.fromtimestamp(float(text), tz=_IST).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    for form in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, form).date().isoformat()
        except ValueError:
            pass
    return None


def _number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


class SymbolRegistry:
    """Classify only exact canonical BankNifty identities and contracts."""

    def __init__(
        self,
        selected_futures: Iterable[str] | None = None,
        selected_by_session: Mapping[str, str | Iterable[str]] | None = None,
    ):
        selected = selected_futures if selected_futures is not None else ()
        self.selected_futures = frozenset(str(symbol) for symbol in selected)
        if any(_FUTURES.fullmatch(symbol) is None for symbol in self.selected_futures):
            raise ValueError("selected futures must be exact canonical BankNifty FUT contracts")
        self.selected_by_session: dict[str, frozenset[str]] = {}
        self._fixed_sessions: set[str] = set()
        for session, value in (selected_by_session or {}).items():
            values = (value,) if isinstance(value, str) else tuple(value)
            contracts = frozenset(str(symbol) for symbol in values)
            if not contracts or any(_FUTURES.fullmatch(symbol) is None for symbol in contracts):
                raise ValueError(f"invalid selected futures for session {session}")
            self.selected_by_session[str(session)] = contracts
            self._fixed_sessions.add(str(session))

    def select_session_futures(
        self,
        session_date: str,
        candidates: Iterable[tuple[object, object, object]],
        *,
        as_of_date: str | None = None,
    ) -> str | None:
        """Select nearest unexpired contract, then greatest OI, deterministically."""
        session = str(session_date)
        if session in self._fixed_sessions:
            return min(self.selected_by_session[session])
        as_of = datetime.strptime(as_of_date or session, "%Y-%m-%d").date()
        ranked: list[tuple[object, float, str]] = []
        for raw_symbol, raw_expiry, raw_oi in candidates:
            symbol = raw_symbol if isinstance(raw_symbol, str) else ""
            match = _FUTURES.fullmatch(symbol)
            expiry = normalize_expiry(raw_expiry)
            if match is None or expiry is None or not self._expiry_matches(match, expiry):
                continue
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            if expiry_date < as_of:
                continue
            oi = _number(raw_oi)
            ranked.append((expiry_date, -float(oi or 0), symbol))
        if not ranked:
            return None
        selected = min(ranked)[2]
        self.selected_by_session[session] = frozenset((selected,))
        return selected

    def selected_futures_for_session(self, session_date: str | None) -> frozenset[str]:
        if session_date is not None and str(session_date) in self.selected_by_session:
            return self.selected_by_session[str(session_date)]
        return self.selected_futures

    def classify(
        self,
        source_symbol: object,
        *,
        source_kind: str = "market",
        expiry: object = None,
        strike: object = None,
        option_type: object = None,
        session_date: str | None = None,
    ) -> SymbolClassification:
        symbol = source_symbol if isinstance(source_symbol, str) else ""
        normalized_expiry = normalize_expiry(expiry)
        if symbol == CANONICAL_INDEX_SYMBOL:
            if source_kind.lower() == "option_chain":
                return self._unknown(
                    symbol, "IGNORED_OPTION_CHAIN_UNDERLYING_REFERENCE"
                )
            return SymbolClassification(InstrumentClass.INDEX, symbol, symbol)
        if expiry not in (None, "") and normalized_expiry is None:
            return self._unknown(symbol, "INVALID_EXPIRY_METADATA")

        futures = _FUTURES.fullmatch(symbol)
        if futures:
            selected = self.selected_futures_for_session(session_date)
            if not selected:
                return self._unknown(symbol, "FUTURES_SELECTION_PENDING")
            if symbol not in selected:
                return self._unknown(symbol, "UNSELECTED_FUTURES_CONTRACT")
            if not self._expiry_matches(futures, normalized_expiry):
                return self._unknown(symbol, "EXPIRY_METADATA_MISMATCH")
            instrument = (
                InstrumentClass.FUTURES_OI
                if source_kind.lower() in {"future_depth", "futures_oi"}
                else InstrumentClass.FUTURES
            )
            return SymbolClassification(
                instrument, symbol, symbol, normalized_expiry,
                reason="VERIFIED_BANKNIFTY_FUTURES_CONTRACT",
            )

        option = _OPTION.fullmatch(symbol)
        if option:
            if source_kind.lower() != "option_chain":
                return self._unknown(symbol, "IGNORED_NONCANONICAL_OPTION_PREMIUM_SOURCE")
            parsed_type = option.group("option_type")
            supplied_type = str(option_type).upper() if option_type not in (None, "") else parsed_type
            parsed_strike = _number(option.group("strike"))
            supplied_strike = _number(strike)
            if strike not in (None, "") and supplied_strike is None:
                return self._unknown(symbol, "INVALID_STRIKE_METADATA")
            if supplied_type != parsed_type:
                return self._unknown(symbol, "OPTION_TYPE_METADATA_MISMATCH")
            if supplied_strike is not None and supplied_strike != parsed_strike:
                return self._unknown(symbol, "STRIKE_METADATA_MISMATCH")
            if not self._expiry_matches(option, normalized_expiry):
                return self._unknown(symbol, "EXPIRY_METADATA_MISMATCH")
            return SymbolClassification(
                InstrumentClass(parsed_type),
                symbol,
                symbol,
                normalized_expiry,
                parsed_strike,
                parsed_type,
                "VERIFIED_BANKNIFTY_OPTION_CONTRACT",
            )

        return self._unknown(symbol, "UNKNOWN_SYMBOL")

    @staticmethod
    def _expiry_matches(match: re.Match[str], expiry: str | None) -> bool:
        if expiry is None:
            return True
        parsed = datetime.strptime(expiry, "%Y-%m-%d")
        return parsed.year == 2000 + int(match.group("year")) and parsed.month == _MONTH_NUMBER[match.group("month")]

    @staticmethod
    def _unknown(symbol: str, reason: str) -> SymbolClassification:
        return SymbolClassification(
            InstrumentClass.UNKNOWN_SYMBOL,
            None,
            symbol,
            reason=reason,
        )


CANONICAL_SYMBOL_REGISTRY = SymbolRegistry()


def classify_symbol(source_symbol: object, **metadata: object) -> SymbolClassification:
    return CANONICAL_SYMBOL_REGISTRY.classify(source_symbol, **metadata)

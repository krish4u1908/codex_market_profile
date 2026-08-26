#!/usr/bin/env python3
"""Build the byte-exact, windowed R6E1R focused raw-data fixture.

The output is a projection, not a rewritten market-data set.  Relevant JSONL
records are copied byte-for-byte.  Excluded complete records before a selected
record become blank JSONL rows in the per-hour collector file so the selected
record keeps its authoritative source-row coordinate.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, BinaryIO, Mapping

from banknifty_profiler.raw_io import reader as raw_reader
from banknifty_profiler.runtime.timestamps import CANONICAL_TIMEZONE, parse_timestamp


CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
INDEX_SYMBOL = "NSE:NIFTYBANK-INDEX"
SCHEMA = "R6E1R_FOCUSED_SAMPLE_V2"
IDENTITY_SCHEMA = "R6E1R_SELECTED_RECORD_IDENTITY_V1"
_SHA256_BLOCK_BYTES = 1 << 20


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _json_line(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_SHA256_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ends_with_newline(path: Path) -> bool:
    if path.stat().st_size == 0:
        return True
    with path.open("rb") as handle:
        handle.seek(-1, os.SEEK_END)
        return handle.read(1) == b"\n"


def _write_blank_rows(handle: BinaryIO, digest: Any, count: int) -> int:
    remaining = count
    block = b"\n" * (1 << 16)
    while remaining:
        value = block if remaining >= len(block) else block[:remaining]
        handle.write(value)
        digest.update(value)
        remaining -= len(value)
    return count


def _window_timestamp(session: str, value: str, *, name: str):
    if not re.fullmatch(r"\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?", value):
        raise ValueError(f"{name} must be an IST wall time such as 09:15 or 12:05:00")
    try:
        naive = datetime.fromisoformat(f"{session}T{value}")
    except ValueError as error:
        raise ValueError(f"invalid {name}: {value!r}") from error
    # The requested session is an IST trading date.  Constructing the explicit
    # offset before using the repository parser avoids accepting a naive causal
    # timestamp anywhere in the extraction path.
    return parse_timestamp(
        naive.isoformat() + "+05:30", field_name=f"focused sample {name} IST"
    )


def _source_hours(start, end) -> tuple[int, ...]:
    if start.date() != end.date() or end <= start:
        raise ValueError("focused sample end must be after start on the same IST session")
    last = end.hour if (end.minute or end.second or end.microsecond or end.nanosecond) else end.hour - 1
    return tuple(range(start.hour, last + 1))


def _source_paths(root: Path, session: str, hours: tuple[int, ...]) -> list[Path]:
    result: list[Path] = []
    for stream, prefix in (("raw", "events"), ("oi", "oi")):
        directory = root / stream / session
        if not directory.is_dir():
            raise ValueError(f"authoritative session stream is missing: {directory}")
        for hour in hours:
            path = directory / f"{prefix}_{hour:02d}.jsonl"
            if not path.is_file():
                raise ValueError(f"required authoritative hourly source is missing: {path}")
            result.append(path)
    return result


def _stable_source_identity(path: Path) -> dict[str, Any]:
    before = path.stat()
    digest = _sha256_file(path)
    after = path.stat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise ValueError(f"authoritative source changed while computing before hash: {path}")
    return {
        "device": before.st_dev,
        "inode": before.st_ino,
        "size": before.st_size,
        "bytes_before": before.st_size,
        "mtime_ns_before": before.st_mtime_ns,
        "sha256": digest,
        "sha256_before": digest,
    }


def _selection(
    record: Mapping[str, Any],
    *,
    stream: str,
    futures_symbol: str,
) -> tuple[Counter[str], Counter[str], dict[str, bool]]:
    """Return outer-record classes, evidence symbols, and OI evidence flags."""
    classes: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    evidence = {"futures_oi": False, "previous_futures_oi": False}
    if stream == "raw":
        message = record.get("message")
        if not isinstance(message, Mapping):
            return classes, symbols, evidence
        symbol = str(message.get("symbol", ""))
        if symbol == INDEX_SYMBOL:
            classes["index"] = 1
            symbols[symbol] = 1
        elif symbol == futures_symbol:
            classes["futures"] = 1
            symbols[symbol] = 1
        return classes, symbols, evidence

    source = record.get("source")
    response = record.get("response")
    if not isinstance(response, Mapping):
        return classes, symbols, evidence
    if source == "future_depth":
        depth = response.get("d")
        payload = depth.get(futures_symbol) if isinstance(depth, Mapping) else None
        if isinstance(payload, Mapping) and payload.get("oi") not in (None, ""):
            classes["futures_oi"] = 1
            symbols[futures_symbol] = 1
            evidence["futures_oi"] = True
            evidence["previous_futures_oi"] = payload.get("pdoi") not in (None, "")
        return classes, symbols, evidence
    if source != "option_chain":
        return classes, symbols, evidence
    data = response.get("data")
    chain = data.get("optionsChain") if isinstance(data, Mapping) else None
    if not isinstance(chain, list):
        return classes, symbols, evidence
    sides: Counter[str] = Counter()
    side_symbols: Counter[str] = Counter()
    for item in chain:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol", ""))
        if not symbol.startswith("NSE:BANKNIFTY"):
            continue
        if symbol.endswith("CE"):
            sides["ce"] += 1
            side_symbols[symbol] += 1
        elif symbol.endswith("PE"):
            sides["pe"] += 1
            side_symbols[symbol] += 1
    # The REST response is the canonical outer record.  Never manufacture a
    # half-chain by retaining an outer response with evidence for only one side.
    if sides["ce"] and sides["pe"]:
        classes.update(sides)
        symbols.update(side_symbols)
    return classes, symbols, evidence


def _candidate_marker(line: bytes, stream: str, futures_symbol: str) -> bool:
    if stream == "raw":
        return INDEX_SYMBOL.encode() in line or futures_symbol.encode() in line
    return (
        b"future_depth" in line and futures_symbol.encode() in line
    ) or b"option_chain" in line


def _close_fsynced(handle: BinaryIO | None) -> None:
    if handle is None:
        return
    handle.flush()
    os.fsync(handle.fileno())
    handle.close()


def build_focused_sample(
    *,
    authoritative_root: Path,
    output_root: Path,
    session: str,
    start_ist: str,
    end_ist: str,
) -> dict[str, Any]:
    source_root = authoritative_root.resolve()
    if not source_root.is_dir() or "research" in source_root.parts:
        raise ValueError("authoritative root must be an existing non-research physical root")
    if not (source_root / "raw").is_dir() or not (source_root / "oi").is_dir():
        raise ValueError("authoritative root must contain raw and oi directories")
    target = output_root.resolve()
    if target.exists():
        raise ValueError("output root must not already exist")

    start = _window_timestamp(session, start_ist, name="start")
    end = _window_timestamp(session, end_ist, name="end")
    if start.date().isoformat() != session or end.date().isoformat() != session:
        raise ValueError("start and end must fall on the requested IST session")
    hours = _source_hours(start, end)
    paths = _source_paths(source_root, session, hours)

    # This is the repository-owned selection authority.  The builder does not
    # infer, configure, or hard-code a Futures contract.
    source_oi = raw_reader.load_oi(source_root / "oi", session)
    futures_symbol, futures_expiry, option_expiry = raw_reader.select_contracts(
        source_oi, session
    )
    if not futures_symbol:
        raise ValueError(f"repository contract discovery failed for {session}")

    before = {str(path): _stable_source_identity(path) for path in paths}
    collector = target / "collector"
    collector.mkdir(parents=True)
    archives = {
        "raw": (target / "raw.jsonl").open("xb"),
        "oi": (target / "oi.jsonl").open("xb"),
    }
    archive_digests = {stream: hashlib.sha256() for stream in archives}
    archive_bytes = Counter()
    archive_rows = Counter()
    selected_records: list[dict[str, Any]] = []
    collector_files: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    record_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    selected_receipts: list[str] = []
    malformed_candidates = 0
    mutation_count = 0
    selected_identity_path = target / "selected_record_identities.jsonl"
    identities = selected_identity_path.open("xb")
    try:
        for source_path in paths:
            relative = source_path.relative_to(source_root)
            stream = relative.parts[0]
            destination = collector / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            output = destination.open("xb")
            output_digest = hashlib.sha256()
            source_read_digest = hashlib.sha256()
            source_offset = 0
            source_row = 0
            projected_offset = 0
            projected_rows = 0
            pending_blank_rows = 0
            selected_count = 0
            incomplete_tail_bytes = 0
            file_counts: Counter[str] = Counter()
            file_receipts: list[str] = []
            try:
                with source_path.open("rb") as source_handle:
                    for line in source_handle:
                        line_offset = source_offset
                        source_offset += len(line)
                        source_read_digest.update(line)
                        if not line.endswith(b"\n"):
                            incomplete_tail_bytes += len(line)
                            continue
                        source_row += 1
                        if not _candidate_marker(line, stream, futures_symbol):
                            pending_blank_rows += 1
                            continue
                        try:
                            record = json.loads(line)
                        except (UnicodeDecodeError, json.JSONDecodeError) as error:
                            malformed_candidates += 1
                            raise ValueError(
                                f"malformed candidate JSONL record: {relative}:{source_row}"
                            ) from error
                        if not isinstance(record, Mapping):
                            malformed_candidates += 1
                            raise ValueError(
                                f"non-object candidate JSONL record: {relative}:{source_row}"
                            )
                        classes, evidence_symbols, oi_evidence = _selection(
                            record, stream=stream, futures_symbol=futures_symbol
                        )
                        if not classes:
                            pending_blank_rows += 1
                            continue
                        receipt = parse_timestamp(
                            record.get("received_at"),
                            field_name="focused sample source receipt timestamp",
                        )
                        if not (start <= receipt < end):
                            pending_blank_rows += 1
                            continue

                        if pending_blank_rows:
                            projected_offset += _write_blank_rows(
                                output, output_digest, pending_blank_rows
                            )
                            projected_rows += pending_blank_rows
                        pending_blank_rows = 0
                        projection_byte_offset = projected_offset
                        output.write(line)
                        output_digest.update(line)
                        projected_offset += len(line)
                        projected_rows += 1

                        archive = archives[stream]
                        combined_offset = archive_bytes[stream]
                        archive.write(line)
                        archive_digests[stream].update(line)
                        archive_bytes[stream] += len(line)
                        archive_rows[stream] += 1

                        selected_count += 1
                        record_counts.update(classes)
                        file_counts.update(classes)
                        symbol_counts.update(evidence_symbols)
                        receipt_text = receipt.isoformat()
                        selected_receipts.append(receipt_text)
                        file_receipts.append(receipt_text)
                        identity = {
                            "identity_schema": IDENTITY_SCHEMA,
                            "source_path": str(source_path),
                            "source_relative_path": str(relative),
                            "source_stream": stream,
                            "source_line": source_row,
                            "source_row": source_row,
                            "source_byte_offset": line_offset,
                            "source_byte_length": len(line),
                            "record_sha256": hashlib.sha256(line).hexdigest(),
                            "receipt_timestamp": receipt_text,
                            "instrument_counts": dict(sorted(classes.items())),
                            "evidence_symbols": dict(sorted(evidence_symbols.items())),
                            "futures_oi_present": oi_evidence["futures_oi"],
                            "previous_futures_oi_present": oi_evidence[
                                "previous_futures_oi"
                            ],
                            "projection_relative_path": str(relative),
                            "projection_row": projected_rows,
                            "projection_byte_offset": projection_byte_offset,
                            "output_file": f"{stream}.jsonl",
                            "output_line": archive_rows[stream],
                            "output_byte_offset": combined_offset,
                        }
                        identities.write(_json_line(identity))
                        selected_records.append(identity)
            finally:
                _close_fsynced(output)

            collector_files.append(
                {
                    "relative_path": str(relative),
                    "bytes": projected_offset,
                    "physical_rows": projected_rows,
                    "selected_json_records": selected_count,
                    "instrument_counts": dict(sorted(file_counts.items())),
                    "first_receipt_timestamp": min(file_receipts) if file_receipts else None,
                    "last_receipt_timestamp": max(file_receipts) if file_receipts else None,
                    "sha256": output_digest.hexdigest(),
                    "ends_with_newline": _ends_with_newline(destination),
                }
            )
            source_entry = {
                "path": str(source_path),
                "relative_path": str(relative),
                **before[str(source_path)],
                "complete_physical_rows": source_row,
                "incomplete_final_bytes_excluded": incomplete_tail_bytes,
                "selected_json_records": selected_count,
                "sha256_during_extraction": source_read_digest.hexdigest(),
            }
            source_files.append(source_entry)
    finally:
        _close_fsynced(identities)
        for handle in archives.values():
            _close_fsynced(handle)

    for row in source_files:
        source_path = Path(row["path"])
        after_stat = source_path.stat()
        after_hash = _sha256_file(source_path)
        row.update(
            {
                "bytes_after": after_stat.st_size,
                "mtime_ns_after": after_stat.st_mtime_ns,
                "sha256_after": after_hash,
            }
        )
        row["unchanged"] = (
            row["device"] == after_stat.st_dev
            and row["inode"] == after_stat.st_ino
            and row["bytes_before"] == after_stat.st_size
            and row["mtime_ns_before"] == after_stat.st_mtime_ns
            and row["sha256_before"] == row["sha256_during_extraction"] == after_hash
        )
        mutation_count += int(not row["unchanged"])
    if mutation_count:
        raise ValueError(f"authoritative sources changed during extraction: {mutation_count}")
    if malformed_candidates:
        raise ValueError(f"malformed candidate records refused: {malformed_candidates}")
    required = ("index", "futures", "futures_oi", "ce", "pe")
    missing = [name for name in required if not record_counts[name]]
    if missing:
        raise ValueError(f"focused sample is missing required evidence: {missing}")

    archive_files = {
        stream: {
            "relative_path": f"{stream}.jsonl",
            "bytes": archive_bytes[stream],
            "selected_json_records": archive_rows[stream],
            "sha256": archive_digests[stream].hexdigest(),
            "ends_with_newline": _ends_with_newline(target / f"{stream}.jsonl"),
        }
        for stream in ("raw", "oi")
    }
    fixture = (
        f"r6e1r0_{start.strftime('%b').lower()}{start.day:02d}_"
        f"{start.strftime('%H%M')}_{end.strftime('%H%M')}"
    )
    manifest = {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "fixture": fixture,
        "authoritative_source_root": str(source_root),
        "collector_root": "collector",
        "session_date": session,
        "window": {
            "timezone": CANONICAL_TIMEZONE,
            "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(),
        },
        "complete_json_lines_only": True,
        "complete_json_records_only": True,
        "selected_records_byte_exact": True,
        "excluded_rows_represented_as_blank_jsonl_for_source_row_preservation": True,
        "incomplete_final_lines_excluded": True,
        "canonical_symbols": {"index": INDEX_SYMBOL, "futures": futures_symbol},
        "contract_selection": {
            "authority": "banknifty_profiler.raw_io.reader.load_oi+select_contracts",
            "futures_symbol": futures_symbol,
            "futures_expiry": str(futures_expiry or ""),
            "option_expiry": str(option_expiry or ""),
            "session_date": session,
        },
        "source_files": source_files,
        "source_mutations": mutation_count,
        "collector_files": collector_files,
        "collector_file_count": len(collector_files),
        "compatibility_archives": archive_files,
        "extracted_sha256": {
            "raw": archive_files["raw"]["sha256"],
            "oi": archive_files["oi"]["sha256"],
        },
        "output_record_counts": dict(sorted(archive_rows.items())),
        "record_counts": dict(sorted(record_counts.items())),
        "instrument_inventory": {
            "index_symbol": INDEX_SYMBOL,
            "selected_futures_symbol": futures_symbol,
            "index_outer_records": record_counts["index"],
            "futures_market_outer_records": record_counts["futures"],
            "futures_oi_outer_records": record_counts["futures_oi"],
            "ce_evidence_items": record_counts["ce"],
            "pe_evidence_items": record_counts["pe"],
            "symbol_counts": dict(sorted(symbol_counts.items())),
        },
        "first_receipt_timestamp": min(selected_receipts),
        "last_receipt_timestamp": max(selected_receipts),
        "selected_outer_records": len(selected_records),
        # Inline identities retain compatibility with the existing focused
        # fixture verifier.  Sources are still scanned one line at a time; no
        # raw record bodies are retained in memory or placed in this manifest.
        "selected_records": selected_records,
        "selected_record_identity_file": {
            "relative_path": selected_identity_path.name,
            "schema": IDENTITY_SCHEMA,
            "rows": len(selected_records),
            "sha256": _sha256_file(selected_identity_path),
        },
        "malformed_candidate_records": malformed_candidates,
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    with manifest_path.open("rb") as handle:
        os.fsync(handle.fileno())
    manifest_sha256 = _sha256_file(manifest_path)
    checksum_path = target / "manifest.sha256"
    checksum_path.write_text(f"{manifest_sha256}  manifest.json\n", encoding="ascii")
    with checksum_path.open("rb") as handle:
        os.fsync(handle.fileno())
    for directory in sorted(
        {target, collector, *(path.parent for path in (collector / Path(row["relative_path"]) for row in collector_files))},
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        _fsync_directory(directory)
    return {**manifest, "manifest_sha256": manifest_sha256}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--session", required=True, help="IST session date, YYYY-MM-DD")
    parser.add_argument("--start-ist", "--start", dest="start_ist", required=True)
    parser.add_argument("--end-ist", "--end", dest="end_ist", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = build_focused_sample(
        authoritative_root=args.authoritative_root,
        output_root=args.output_root,
        session=args.session,
        start_ist=args.start_ist,
        end_ist=args.end_ist,
    )
    print(
        json.dumps(
            {
                "classification": CLASSIFICATION,
                "collector_file_count": manifest["collector_file_count"],
                "manifest_sha256": manifest["manifest_sha256"],
                "output_root": str(args.output_root.resolve()),
                "selected_outer_records": manifest["selected_outer_records"],
                "source_mutations": manifest["source_mutations"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

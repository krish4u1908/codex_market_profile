from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import Lock

from banknifty_profiler.runtime.timestamps import parse_timestamp


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _encode_row(row: dict) -> bytes:
    return (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()


_AUDIT_IDENTITY_FIELDS = (
    "event_id", "transition_id", "record_id", "episode_id",
    "observation_id",
)
_AUDIT_EVIDENCE_FIELDS = (
    "effective_timestamp", "confirmation_timestamp",
    "state_entry_timestamp", "observation_timestamp",
    "receipt_timestamp", "evidence_receipt_timestamp",
    "availability_timestamp", "control_effective_timestamp",
    "index_receipt_timestamp", "futures_receipt_timestamp",
)
_AUDIT_TAIL_LIMIT = 500


def _metadata(stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
        stat.st_ctime_ns,
    )


def _row_identity(row: dict) -> str | None:
    for field in _AUDIT_IDENTITY_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _row_backdated(row: dict, *, path: Path, ordinal: int) -> bool:
    publication = None
    if "publication_timestamp" in row and row["publication_timestamp"] is not None:
        publication = parse_timestamp(
            row["publication_timestamp"],
            field_name=f"ledger publication timestamp at row {ordinal} ({path})",
        )
    evidence = []
    for field in _AUDIT_EVIDENCE_FIELDS:
        if field not in row or row[field] is None:
            continue
        evidence.append(parse_timestamp(
            row[field], field_name=f"ledger {field} at row {ordinal} ({path})",
        ))
    return publication is not None and any(value > publication for value in evidence)


@dataclass(frozen=True, slots=True)
class LedgerBoundary:
    """Stable end-of-ledger identity captured immediately before an append."""

    existed: bool
    device: int | None
    inode: int | None
    size: int
    mtime_ns: int | None = None
    ctime_ns: int | None = None
    content_chain_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class LedgerAppendReceipt:
    """Opaque proof for one durable append awaiting caller acceptance.

    The ledger permits only one unresolved receipt at a time.  The caller must
    make the committed identities visible to its own durable/in-memory state
    before acknowledging this receipt; until then every later append refuses.
    """

    ledger_name: str
    intent_sha256: str
    declared_identities: tuple[str, ...]
    committed_identities: tuple[str, ...]
    ledger_size: int
    content_chain_sha256: str


@dataclass(slots=True)
class _LedgerAudit:
    existed: bool
    device: int | None
    inode: int | None
    size: int
    mtime_ns: int | None
    ctime_ns: int | None
    row_count: int
    duplicate_ids: int
    timestamp_backdating: int
    tail: deque[dict]
    hasher: object


class AppendOnlyLedger:
    """A newline-delimited ledger whose acknowledged appends are durable."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._audit: _LedgerAudit | None = None
        self._append_intent_path = path.with_name(
            path.name + ".append_intent.json"
        )
        self._append_quarantine_path = path.with_name(
            path.name + ".append_quarantine.json"
        )
        self._append_quarantined = False

    def append(self, row: dict) -> None:
        self.append_many([row])

    def append_many(self, rows) -> None:
        self._append_many(rows, retain_intent=False)

    def append_many_retained(self, rows) -> LedgerAppendReceipt | None:
        """Durably append rows while retaining the intent for caller ACK.

        This is the caller-wide transaction boundary used by the analytical
        observation stage.  A hard crash after the data fsync but before the
        caller accepts the rows leaves the generic append intent on disk.
        """
        return self._append_many(rows, retain_intent=True)

    def _append_many(
        self, rows, *, retain_intent: bool,
    ) -> LedgerAppendReceipt | None:
        values, encoded_rows = self._prepare_rows(rows, context="append")
        if not values:
            return None
        encoded = b"".join(encoded_rows)
        with self._lock:
            recovered = self._recover_persisted_append_intent_locked(
                clear_committed=False,
            )
            if self._append_intent_path.exists():
                detail = (
                    "recovered a committed append; caller reconciliation is "
                    "required"
                    if recovered else "has an unresolved append intent"
                )
                raise ValueError(
                    f"append-only ledger {detail}: {self.path}"
                )
            self._ensure_audit_locked()
            before = self._verify_trusted_locked()
            existed = before is not None
            boundary = LedgerBoundary(
                existed,
                before.st_dev if before is not None else None,
                before.st_ino if before is not None else None,
                before.st_size if before is not None else 0,
                before.st_mtime_ns if before is not None else None,
                before.st_ctime_ns if before is not None else None,
                self._audit.hasher.hexdigest(),
            )
            self._write_persisted_append_intent_locked(
                boundary, values, encoded_rows
            )
            try:
                with self.path.open("ab") as handle:
                    opened = os.fstat(handle.fileno())
                    if existed and _metadata(opened) != _metadata(before):
                        raise ValueError(
                            f"append-only ledger changed before append: {self.path}"
                        )
                    if not existed and opened.st_size:
                        raise ValueError(
                            f"append-only ledger appeared before append: {self.path}"
                        )
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                    written = os.fstat(handle.fileno())
                expected_size = (
                    before.st_size if before is not None else 0
                ) + len(encoded)
                if written.st_size != expected_size:
                    raise ValueError(
                        f"append-only ledger has an unexpected concurrent tail: "
                        f"{self.path}"
                    )
                # A new directory entry needs its own durability boundary.
                if not existed:
                    _fsync_directory(self.path.parent)
                after = self.path.stat()
                if _metadata(after) != _metadata(written):
                    raise ValueError(
                        f"append-only ledger changed during append: {self.path}"
                    )
                self._advance_audit_locked(values, encoded_rows, after)
                if retain_intent:
                    return self._retained_append_receipt_locked(
                        tuple(
                            str(_row_identity(row)) for row in values
                        )
                    )
                self._clear_persisted_append_intent_locked()
                return None
            except Exception:
                # Keep the durable declaration. Same-process reconciliation or
                # restart recovery can accept only its exact complete prefix.
                raise

    def append_boundary(self) -> LedgerBoundary:
        """Capture a constant-size append boundary without reading the ledger.

        The last-byte check prevents recovery from treating an already partial
        JSONL record as the beginning of the attempted append.
        """
        with self._lock:
            recovered = self._recover_persisted_append_intent_locked(
                clear_committed=False,
            )
            if self._append_intent_path.exists():
                detail = (
                    "recovered a committed append; caller reconciliation is "
                    "required"
                    if recovered else "has an unresolved append intent"
                )
                raise ValueError(
                    f"append-only ledger {detail}: {self.path}"
                )
            self._ensure_audit_locked()
            stat = self._verify_trusted_locked()
            if stat is None:
                return LedgerBoundary(
                    False, None, None, 0, None, None,
                    hashlib.sha256().hexdigest(),
                )
            if stat.st_size:
                with self.path.open("rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if _metadata(opened) != _metadata(stat):
                        raise ValueError(
                            f"append-only ledger changed at append boundary: {self.path}"
                        )
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) != b"\n":
                        raise ValueError(
                            f"append-only ledger has a partial final line: {self.path}"
                        )
            return LedgerBoundary(
                True, stat.st_dev, stat.st_ino, stat.st_size,
                stat.st_mtime_ns, stat.st_ctime_ns,
                self._audit.hasher.hexdigest(),
            )

    def reconcile_appended_prefix(
        self,
        boundary: LedgerBoundary,
        rows,
        *,
        identity_field: str,
    ) -> tuple[str, ...]:
        """Reconcile an ambiguous append and quarantine every mismatch."""
        committed, _receipt = self._reconcile_append_transaction(
            boundary, rows, identity_field=identity_field,
            retain_intent=False,
        )
        return committed

    def reconcile_retained_append(
        self,
        boundary: LedgerBoundary,
        rows,
        *,
        identity_field: str,
    ) -> LedgerAppendReceipt:
        """Recover an exact append prefix while retaining its caller intent."""
        _committed, receipt = self._reconcile_append_transaction(
            boundary, rows, identity_field=identity_field,
            retain_intent=True,
        )
        if receipt is None:  # pragma: no cover - guarded by retain_intent
            raise ValueError(f"ledger recovery produced no receipt: {self.path}")
        return receipt

    def _reconcile_append_transaction(
        self,
        boundary: LedgerBoundary,
        rows,
        *,
        identity_field: str,
        retain_intent: bool,
    ) -> tuple[tuple[str, ...], LedgerAppendReceipt | None]:
        values, encoded_rows = self._prepare_rows(rows, context="recovery")
        try:
            # The caller-level boundary can precede the internal append
            # declaration (or outlive its successful clear).  Persist that
            # exact attempted tail before inspecting any ambiguous bytes so a
            # failed quarantine-marker sync still leaves a restart barrier.
            with self._lock:
                if (
                    self._append_quarantined
                    or self._append_quarantine_path.exists()
                ):
                    raise ValueError(
                        f"append-only ledger is quarantined: {self.path}"
                    )
                if (
                    not self._append_intent_path.exists()
                ):
                    self._write_persisted_append_intent_locked(
                        boundary, values, encoded_rows,
                    )
                else:
                    self._assert_persisted_intent_matches_locked(
                        boundary, values, encoded_rows,
                    )
            committed = self._reconcile_appended_prefix(
                boundary, values, identity_field=identity_field
            )
            with self._lock:
                self._assert_persisted_intent_matches_locked(
                    boundary, values, encoded_rows,
                )
                if retain_intent:
                    return committed, self._retained_append_receipt_locked(
                        committed
                    )
                self._clear_persisted_append_intent_locked()
            return committed, None
        except Exception as recovery_error:
            self._append_quarantined = True
            if not self._append_quarantine_path.exists():
                try:
                    atomic_json(self._append_quarantine_path, {
                        "version": "R6E1R_LEDGER_APPEND_QUARANTINE_V1",
                        "ledger_name": self.path.name,
                        "boundary_size": getattr(boundary, "size", None),
                        "reason": type(recovery_error).__name__,
                    })
                except Exception:
                    # Any pre-existing intent remains a durable retry barrier.
                    # The live instance is poisoned even if marker sync fails.
                    pass
            raise

    def _reconcile_appended_prefix(
        self,
        boundary: LedgerBoundary,
        rows,
        *,
        identity_field: str,
    ) -> tuple[str, ...]:
        """Return the exact complete-row prefix durably written after ``boundary``.

        This is only for an ambiguous exceptional append.  Recovery reads at
        most the encoded attempted batch, verifies byte-for-byte prefix order,
        and refuses partial, replaced, concurrent, or otherwise unexpected
        tails.  A second fsync makes a visible complete prefix durable even if
        the original exception came from an ambiguous sync boundary.
        """
        values, encoded_rows = self._prepare_rows(rows, context="recovery")
        identities: list[str] = []
        seen: set[str] = set()
        for ordinal, row in enumerate(values, start=1):
            identity = row.get(identity_field)
            if not isinstance(identity, str) or not identity:
                raise ValueError(
                    f"ledger recovery row {ordinal} has no {identity_field}: {self.path}"
                )
            if identity in seen:
                raise ValueError(
                    f"duplicate attempted ledger identity {identity}: {self.path}"
                )
            seen.add(identity)
            identities.append(identity)
        maximum_tail = sum(map(len, encoded_rows))

        with self._lock:
            self._ensure_audit_locked()
            try:
                before_read = self.path.stat()
            except FileNotFoundError:
                if boundary.existed:
                    raise ValueError(
                        f"append-only ledger disappeared during append: {self.path}"
                    )
                return ()
            if boundary.existed and (
                before_read.st_dev != boundary.device
                or before_read.st_ino != boundary.inode
            ):
                raise ValueError(
                    f"append-only ledger was replaced during append: {self.path}"
                )
            if before_read.st_size < boundary.size:
                raise ValueError(
                    f"append-only ledger was truncated during append: {self.path}"
                )
            tail_size = before_read.st_size - boundary.size
            if tail_size > maximum_tail:
                raise ValueError(
                    f"append-only ledger has an unexpected concurrent tail: {self.path}"
                )
            with self.path.open("rb") as handle:
                prefix_hasher = hashlib.sha256()
                remaining = boundary.size
                while remaining:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError(
                            f"append-only ledger prefix was truncated during append: "
                            f"{self.path}"
                        )
                    prefix_hasher.update(chunk)
                    remaining -= len(chunk)
                if not boundary.content_chain_sha256:
                    raise ValueError(
                        f"append-only ledger boundary has no authenticated prefix: "
                        f"{self.path}"
                    )
                if prefix_hasher.hexdigest() != boundary.content_chain_sha256:
                    raise ValueError(
                        f"append-only ledger authenticated prefix changed during "
                        f"append: {self.path}"
                    )
                handle.seek(boundary.size)
                tail = handle.read(tail_size + 1)
                handle_stat = os.fstat(handle.fileno())
            try:
                after_read = self.path.stat()
            except FileNotFoundError as error:
                raise ValueError(
                    f"append-only ledger disappeared during recovery: {self.path}"
                ) from error
            stable_identity = _metadata(before_read)
            if (
                len(tail) != tail_size
                or _metadata(handle_stat) != stable_identity
                or _metadata(after_read) != stable_identity
            ):
                raise ValueError(
                    f"append-only ledger changed during recovery: {self.path}"
                )

            cursor = 0
            committed: list[str] = []
            for identity, encoded in zip(identities, encoded_rows, strict=True):
                end = cursor + len(encoded)
                if end > len(tail):
                    break
                if tail[cursor:end] != encoded:
                    raise ValueError(
                        f"append-only ledger tail differs from attempted rows: {self.path}"
                    )
                committed.append(identity)
                cursor = end
            if cursor != len(tail):
                raise ValueError(
                    f"append-only ledger has a partial or mismatched appended line: {self.path}"
                )

            # A visible prefix can follow a failed file or directory fsync.
            # Repeat both durability operations before allowing its identities
            # into an in-memory seen set.  The original append exception is
            # still propagated by the caller, so no source/outbox ACK follows.
            with self.path.open("ab") as handle:
                sync_stat = os.fstat(handle.fileno())
                if _metadata(sync_stat) != stable_identity:
                    raise ValueError(
                        f"append-only ledger changed before recovery fsync: {self.path}"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            try:
                after_sync = self.path.stat()
            except FileNotFoundError as error:
                raise ValueError(
                    f"append-only ledger disappeared after recovery fsync: {self.path}"
                ) from error
            if _metadata(after_sync) != stable_identity:
                raise ValueError(
                    f"append-only ledger changed after recovery fsync: {self.path}"
                )
            if not boundary.existed:
                _fsync_directory(self.path.parent)
            actual_hasher = prefix_hasher.copy()
            actual_hasher.update(tail)
            self._reconcile_audit_locked(
                boundary, values[:len(committed)],
                encoded_rows[:len(committed)], after_sync,
                actual_digest=actual_hasher.hexdigest(),
            )
            return tuple(committed)

    def rows(self):
        with self._lock:
            self._recover_persisted_append_intent_locked()
            if self._audit is not None:
                self._verify_trusted_locked()
            return self._read_and_prime_locked()

    def rows_with_retained_append(
        self,
    ) -> tuple[list[dict], LedgerAppendReceipt | None]:
        """Read the ledger while leaving a recovered caller intent unresolved.

        Startup users accept the returned rows into caller-owned state and only
        then acknowledge the optional receipt.  Thus a second crash anywhere
        before caller acceptance repeats the same bounded recovery.
        """
        with self._lock:
            committed = self._recover_persisted_append_intent_locked(
                clear_committed=False,
            )
            pending = self._append_intent_path.is_file()
            if self._audit is not None:
                self._verify_trusted_locked()
            rows = self._read_and_prime_locked()
            receipt = (
                self._retained_append_receipt_locked(committed)
                if pending else None
            )
            return rows, receipt

    def has_retained_append(self) -> bool:
        """Return whether caller acceptance still owes an explicit ACK."""
        with self._lock:
            if self._append_quarantined or self._append_quarantine_path.exists():
                raise ValueError(f"append-only ledger is quarantined: {self.path}")
            return self._append_intent_path.is_file()

    def acknowledge_retained_append(
        self,
        receipt: LedgerAppendReceipt,
        *,
        accepted_identities,
    ) -> None:
        """Clear exactly one retained intent after caller-visible acceptance."""
        if not isinstance(receipt, LedgerAppendReceipt):
            raise TypeError("retained append acknowledgement requires its receipt")
        accepted = tuple(str(identity) for identity in accepted_identities)
        if accepted != receipt.committed_identities:
            raise ValueError(
                f"retained append ACK identities differ from receipt: {self.path}"
            )
        with self._lock:
            if self._append_quarantined or self._append_quarantine_path.exists():
                raise ValueError(f"append-only ledger is quarantined: {self.path}")
            if not self._append_intent_path.is_file():
                raise ValueError(
                    f"append-only ledger has no retained intent to ACK: {self.path}"
                )
            self._ensure_audit_locked()
            self._verify_trusted_locked()
            try:
                current = self._retained_append_receipt_locked(
                    receipt.committed_identities
                )
            except ValueError as error:
                raise ValueError(
                    f"retained append ACK receipt is stale or mismatched: "
                    f"{self.path}"
                ) from error
            if current != receipt:
                raise ValueError(
                    f"retained append ACK receipt is stale or mismatched: {self.path}"
                )
            self._clear_persisted_append_intent_locked()

    def audit_snapshot(self) -> dict[str, object]:
        """Return the trusted constant-memory audit view without scanning.

        Startup callers prime this view while performing their mandatory
        ``rows()`` identity validation.  Normal appends and bounded ambiguity
        recovery advance it transactionally.  Any external metadata change,
        including a same-size in-place rewrite, invalidates the view.
        """
        with self._lock:
            self._recover_persisted_append_intent_locked()
            if self._audit is None:
                try:
                    self.path.stat()
                except FileNotFoundError:
                    self._audit = self._empty_audit()
                else:
                    raise ValueError(
                        f"append-only ledger audit is not startup-primed: {self.path}"
                    )
            self._verify_trusted_locked()
            return {
                "row_count": self._audit.row_count,
                "duplicate_ids": self._audit.duplicate_ids,
                "timestamp_backdating": self._audit.timestamp_backdating,
                "tail": [dict(row) for row in self._audit.tail],
                "generation": (
                    self._audit.existed,
                    self._audit.device,
                    self._audit.inode,
                    self._audit.size,
                    self._audit.mtime_ns,
                    self._audit.ctime_ns,
                    self._audit.hasher.hexdigest(),
                ),
            }

    def scan_from(self, boundary: LedgerBoundary | None, consume) -> LedgerBoundary:
        """Stream complete rows appended after a stable prior boundary.

        Unlike :meth:`rows`, this method never materializes the ledger.  The
        consumer is called once per decoded row while file identity and size
        are held stable against appends through this ledger instance.  A
        replacement, truncation, partial line, or concurrent external write is
        refused; callers should commit derived counters only after this method
        returns its new boundary.
        """
        with self._lock:
            self._recover_persisted_append_intent_locked()
            try:
                before = self.path.stat()
            except FileNotFoundError:
                if boundary is not None and boundary.existed:
                    raise ValueError(
                        f"append-only ledger disappeared during scan: {self.path}"
                    )
                return LedgerBoundary(
                    False, None, None, 0, None, None,
                    hashlib.sha256().hexdigest(),
                )

            start = boundary.size if boundary is not None else 0
            if boundary is not None and boundary.existed and (
                before.st_dev != boundary.device
                or before.st_ino != boundary.inode
            ):
                raise ValueError(
                    f"append-only ledger was replaced during scan: {self.path}"
                )
            if before.st_size < start:
                raise ValueError(
                    f"append-only ledger was truncated during scan: {self.path}"
                )
            if boundary is not None and before.st_size == boundary.size and (
                boundary.mtime_ns not in (None, before.st_mtime_ns)
                or boundary.ctime_ns not in (None, before.st_ctime_ns)
            ):
                raise ValueError(
                    f"append-only ledger prefix changed during scan: {self.path}"
                )

            with self.path.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                if _metadata(opened) != _metadata(before):
                    raise ValueError(
                        f"append-only ledger changed before scan: {self.path}"
                    )
                chain = hashlib.sha256()
                remaining = start
                last_byte = b""
                while remaining:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError(
                            f"append-only ledger boundary was truncated: {self.path}"
                        )
                    chain.update(chunk)
                    last_byte = chunk[-1:]
                    remaining -= len(chunk)
                if start and last_byte != b"\n":
                    raise ValueError(
                        f"append-only ledger boundary is not complete: {self.path}"
                    )
                if boundary is not None:
                    expected = boundary.content_chain_sha256
                    if not expected:
                        raise ValueError(
                            f"append-only ledger boundary has no authenticated prefix: "
                            f"{self.path}"
                        )
                    if chain.hexdigest() != expected:
                        raise ValueError(
                            f"append-only ledger authenticated prefix changed during "
                            f"scan: {self.path}"
                        )
                offset = start
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        raise ValueError(
                            f"append-only ledger has a partial line at byte "
                            f"{offset}: {self.path}"
                        )
                    offset += len(line)
                    if not line.strip():
                        raise ValueError(
                            f"append-only ledger has a blank line ending at "
                            f"byte {offset}: {self.path}"
                        )
                    chain.update(line)
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        raise ValueError(
                            f"append-only ledger has a corrupt line ending at "
                            f"byte {offset}: {self.path}"
                        ) from error
                    if not isinstance(row, dict):
                        raise ValueError(
                            f"append-only ledger row ending at byte {offset} is not "
                            f"an object: {self.path}"
                        )
                    consume(row)
                opened_after = os.fstat(handle.fileno())
            try:
                after = self.path.stat()
            except FileNotFoundError as error:
                raise ValueError(
                    f"append-only ledger disappeared after scan: {self.path}"
                ) from error
            stable = _metadata(before)
            if (
                _metadata(opened_after) != stable
                or _metadata(after) != stable
                or offset != before.st_size
            ):
                raise ValueError(
                    f"append-only ledger changed during scan: {self.path}"
                )
            return LedgerBoundary(
                True, before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns, chain.hexdigest(),
            )

    def _write_persisted_append_intent_locked(
        self,
        boundary: LedgerBoundary,
        rows: list[dict],
        encoded_rows: list[bytes],
    ) -> None:
        """Declare the only physical tail that a restart may promote."""
        if self._append_intent_path.exists():
            raise ValueError(
                f"append-only ledger has an unresolved append intent: {self.path}"
            )
        expected = []
        for row, encoded in zip(rows, encoded_rows, strict=True):
            identity = _row_identity(row)
            if identity is None:
                raise ValueError(
                    f"append-only ledger intent row has no identity: {self.path}"
                )
            expected.append({
                "identity": identity,
                "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
                "encoded_size": len(encoded),
            })
        atomic_json(self._append_intent_path, {
            "version": "R6E1R_LEDGER_APPEND_INTENT_V1",
            "ledger_name": self.path.name,
            "boundary": {
                field: getattr(boundary, field)
                for field in (
                    "existed", "device", "inode", "size", "mtime_ns",
                    "ctime_ns", "content_chain_sha256",
                )
            },
            "expected": expected,
            "expected_encoded_bytes": sum(map(len, encoded_rows)),
        })

    def _read_persisted_append_intent_locked(self) -> tuple[dict, bytes]:
        """Read one intent under a stable inode/metadata identity."""
        try:
            before = self._append_intent_path.stat()
        except FileNotFoundError as error:
            raise ValueError(
                f"append-only ledger has no persisted append intent: {self.path}"
            ) from error
        with self._append_intent_path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _metadata(opened) != _metadata(before):
                raise ValueError("ledger append intent changed before read")
            encoded = handle.read()
            opened_after = os.fstat(handle.fileno())
        try:
            after = self._append_intent_path.stat()
        except FileNotFoundError as error:
            raise ValueError("ledger append intent disappeared during read") from error
        if (
            _metadata(opened_after) != _metadata(before)
            or _metadata(after) != _metadata(before)
        ):
            raise ValueError("ledger append intent changed during read")
        try:
            value = json.loads(encoded)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("invalid ledger append intent JSON") from error
        if not isinstance(value, dict):
            raise ValueError("invalid ledger append intent object")
        return value, encoded

    def _assert_persisted_intent_matches_locked(
        self,
        boundary: LedgerBoundary,
        rows: list[dict],
        encoded_rows: list[bytes],
    ) -> None:
        """Bind exceptional reconciliation to the existing declaration."""
        raw, _encoded = self._read_persisted_append_intent_locked()
        expected_boundary = {
            field: getattr(boundary, field)
            for field in (
                "existed", "device", "inode", "size", "mtime_ns",
                "ctime_ns", "content_chain_sha256",
            )
        }
        expected_rows = [
            {
                "identity": str(_row_identity(row)),
                "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
                "encoded_size": len(encoded),
            }
            for row, encoded in zip(rows, encoded_rows, strict=True)
        ]
        if (
            raw.get("version") != "R6E1R_LEDGER_APPEND_INTENT_V1"
            or raw.get("ledger_name") != self.path.name
            or raw.get("boundary") != expected_boundary
            or raw.get("expected") != expected_rows
            or raw.get("expected_encoded_bytes")
            != sum(map(len, encoded_rows))
        ):
            raise ValueError(
                f"ledger append intent differs from attempted rows: {self.path}"
            )

    def _retained_append_receipt_locked(
        self, committed_identities: tuple[str, ...],
    ) -> LedgerAppendReceipt:
        """Seal a current, already-validated intent and ledger generation."""
        raw, encoded = self._read_persisted_append_intent_locked()
        expected = raw.get("expected")
        if (
            raw.get("version") != "R6E1R_LEDGER_APPEND_INTENT_V1"
            or raw.get("ledger_name") != self.path.name
            or not isinstance(expected, list)
        ):
            raise ValueError("invalid retained ledger append intent envelope")
        declared: list[str] = []
        for item in expected:
            if not isinstance(item, dict):
                raise ValueError("invalid retained ledger append intent row")
            identity = item.get("identity")
            if not isinstance(identity, str) or not identity:
                raise ValueError("invalid retained ledger append identity")
            declared.append(identity)
        if len(set(declared)) != len(declared):
            raise ValueError("duplicate retained ledger append identity")
        if tuple(declared[:len(committed_identities)]) != committed_identities:
            raise ValueError("retained append committed identities are not a prefix")
        audit = self._audit
        if audit is None:
            raise ValueError(f"append-only ledger audit is not primed: {self.path}")
        return LedgerAppendReceipt(
            ledger_name=self.path.name,
            intent_sha256=hashlib.sha256(encoded).hexdigest(),
            declared_identities=tuple(declared),
            committed_identities=committed_identities,
            ledger_size=audit.size,
            content_chain_sha256=audit.hasher.hexdigest(),
        )

    def _clear_persisted_append_intent_locked(self) -> None:
        try:
            self._append_intent_path.unlink()
        except FileNotFoundError:
            return
        _fsync_directory(self.path.parent)

    @staticmethod
    def _valid_sha256(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    def _recover_persisted_append_intent_locked(
        self,
        *,
        clear_committed: bool = True,
    ) -> tuple[str, ...]:
        """Fsync an exact declared prefix or persistently quarantine the ledger."""
        if self._append_quarantined or self._append_quarantine_path.exists():
            raise ValueError(f"append-only ledger is quarantined: {self.path}")
        if not self._append_intent_path.is_file():
            return ()
        boundary: LedgerBoundary | None = None
        try:
            raw = json.loads(self._append_intent_path.read_text())
            if (
                not isinstance(raw, dict)
                or raw.get("version") != "R6E1R_LEDGER_APPEND_INTENT_V1"
                or raw.get("ledger_name") != self.path.name
            ):
                raise ValueError("invalid ledger append intent envelope")
            raw_boundary = raw.get("boundary")
            raw_expected = raw.get("expected")
            expected_bytes = raw.get("expected_encoded_bytes")
            if not isinstance(raw_boundary, dict) or not isinstance(
                raw_expected, list
            ):
                raise ValueError("invalid ledger append intent content")
            boundary = LedgerBoundary(**{
                field: raw_boundary.get(field)
                for field in (
                    "existed", "device", "inode", "size", "mtime_ns",
                    "ctime_ns", "content_chain_sha256",
                )
            })
            if (
                not isinstance(boundary.existed, bool)
                or isinstance(boundary.size, bool)
                or not isinstance(boundary.size, int)
                or boundary.size < 0
                or not self._valid_sha256(boundary.content_chain_sha256)
                or isinstance(expected_bytes, bool)
                or not isinstance(expected_bytes, int)
                or expected_bytes < 0
            ):
                raise ValueError("invalid ledger append intent boundary")
            expected: list[tuple[str, str, int]] = []
            for item in raw_expected:
                if not isinstance(item, dict):
                    raise ValueError("invalid ledger append intent row")
                identity = item.get("identity")
                digest = item.get("encoded_sha256")
                size = item.get("encoded_size")
                if (
                    not isinstance(identity, str)
                    or not identity
                    or not self._valid_sha256(digest)
                    or isinstance(size, bool)
                    or not isinstance(size, int)
                    or size <= 0
                ):
                    raise ValueError("invalid ledger append intent row")
                expected.append((identity, digest, size))
            if (
                len({identity for identity, _digest, _size in expected})
                != len(expected)
                or sum(size for _identity, _digest, size in expected)
                != expected_bytes
            ):
                raise ValueError("invalid ledger append intent bounds")

            try:
                before = self.path.stat()
            except FileNotFoundError:
                before = None
            if before is None:
                if boundary.existed:
                    raise ValueError("declared ledger disappeared")
                prefix_digest = hashlib.sha256().hexdigest()
                tail = b""
            else:
                if boundary.existed and (
                    before.st_dev != boundary.device
                    or before.st_ino != boundary.inode
                ):
                    raise ValueError("declared ledger was replaced")
                if (
                    before.st_size < boundary.size
                    or before.st_size > boundary.size + expected_bytes
                ):
                    raise ValueError("ledger tail exceeds declared bounds")
                with self.path.open("rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if _metadata(opened) != _metadata(before):
                        raise ValueError("ledger changed before intent recovery")
                    hasher = hashlib.sha256()
                    remaining = boundary.size
                    last_byte = b""
                    while remaining:
                        chunk = handle.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("declared ledger prefix was truncated")
                        hasher.update(chunk)
                        last_byte = chunk[-1:]
                        remaining -= len(chunk)
                    if boundary.size and last_byte != b"\n":
                        raise ValueError("declared ledger boundary is partial")
                    tail = handle.read(expected_bytes + 1)
                    opened_after = os.fstat(handle.fileno())
                after = self.path.stat()
                if (
                    _metadata(opened_after) != _metadata(before)
                    or _metadata(after) != _metadata(before)
                    or len(tail) != before.st_size - boundary.size
                ):
                    raise ValueError("ledger changed during intent recovery")
                prefix_digest = hasher.hexdigest()
            if prefix_digest != boundary.content_chain_sha256:
                raise ValueError("declared ledger prefix identity changed")

            cursor = 0
            committed: list[str] = []
            for identity, digest, size in expected:
                if cursor == len(tail):
                    break
                if cursor + size > len(tail):
                    raise ValueError("ledger has a partial declared append row")
                encoded = tail[cursor:cursor + size]
                if hashlib.sha256(encoded).hexdigest() != digest:
                    raise ValueError("ledger tail differs from declared append")
                try:
                    decoded = json.loads(encoded)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise ValueError("ledger declared append row is corrupt") from error
                if not isinstance(decoded, dict) or _row_identity(decoded) != identity:
                    raise ValueError("ledger declared append identity differs")
                committed.append(identity)
                cursor += size
            if cursor != len(tail):
                raise ValueError("ledger contains an unrelated append tail")

            # A complete visible prefix can follow an interrupted fsync. Make
            # both its bytes and (for a new file) directory entry durable before
            # removing the declaration and allowing startup identity priming.
            if before is not None:
                with self.path.open("ab") as handle:
                    current = os.fstat(handle.fileno())
                    if _metadata(current) != _metadata(before):
                        raise ValueError("ledger changed before recovery fsync")
                    handle.flush()
                    os.fsync(handle.fileno())
                after_sync = self.path.stat()
                if _metadata(after_sync) != _metadata(before):
                    raise ValueError("ledger changed after recovery fsync")
                if not boundary.existed:
                    _fsync_directory(self.path.parent)
            self._audit = None
            if not clear_committed:
                # Do not silently turn a direct retry (including an intent
                # whose physical prefix is still empty) into a later append.
                # Caller acceptance plus an explicit ACK owns intent removal.
                return tuple(committed)
            self._clear_persisted_append_intent_locked()
            return tuple(committed)
        except Exception as recovery_error:
            self._append_quarantined = True
            try:
                atomic_json(self._append_quarantine_path, {
                    "version": "R6E1R_LEDGER_APPEND_QUARANTINE_V1",
                    "ledger_name": self.path.name,
                    "boundary_size": getattr(boundary, "size", None),
                    "reason": type(recovery_error).__name__,
                })
            except Exception:
                # The durable intent remains, so a restart must retry and fail
                # closed even when the quarantine marker itself cannot sync.
                pass
            raise ValueError(
                f"append-only ledger recovery is quarantined: {self.path}"
            ) from recovery_error

    def _prepare_rows(self, rows, *, context: str) -> tuple[list[dict], list[bytes]]:
        values = list(rows)
        canonical: list[dict] = []
        encoded_rows: list[bytes] = []
        seen: set[str] = set()
        for ordinal, row in enumerate(values, start=1):
            if not isinstance(row, dict):
                raise ValueError(
                    f"ledger {context} row {ordinal} is not an object: {self.path}"
                )
            identity = _row_identity(row)
            if identity is None:
                raise ValueError(
                    f"ledger {context} row {ordinal} has no supported "
                    f"audit identity: {self.path}"
                )
            if identity in seen:
                raise ValueError(
                    f"duplicate within-batch ledger identity {identity}: {self.path}"
                )
            seen.add(identity)
            encoded = _encode_row(row)
            stable_row = json.loads(encoded)
            _row_backdated(stable_row, path=self.path, ordinal=ordinal)
            canonical.append(stable_row)
            encoded_rows.append(encoded)
        return canonical, encoded_rows

    @staticmethod
    def _empty_audit() -> _LedgerAudit:
        return _LedgerAudit(
            existed=False, device=None, inode=None, size=0,
            mtime_ns=None, ctime_ns=None, row_count=0, duplicate_ids=0,
            timestamp_backdating=0, tail=deque(maxlen=_AUDIT_TAIL_LIMIT),
            hasher=hashlib.sha256(),
        )

    def _ensure_audit_locked(self) -> None:
        if self._audit is None:
            self._read_and_prime_locked()

    def _verify_trusted_locked(self) -> os.stat_result | None:
        audit = self._audit
        if audit is None:
            raise ValueError(f"append-only ledger audit is not primed: {self.path}")
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            if audit.existed:
                raise ValueError(
                    f"append-only ledger disappeared after trusted access: {self.path}"
                )
            return None
        if not audit.existed or _metadata(stat) != (
            audit.device, audit.inode, audit.size, audit.mtime_ns, audit.ctime_ns,
        ):
            raise ValueError(
                f"append-only ledger changed after trusted access: {self.path}"
            )
        return stat

    def _read_and_prime_locked(self) -> list[dict]:
        try:
            handle = self.path.open("rb")
        except FileNotFoundError:
            self._audit = self._empty_audit()
            return []
        result: list[dict] = []
        identities: set[str] = set()
        duplicate_ids = 0
        backdating = 0
        tail: deque[dict] = deque(maxlen=_AUDIT_TAIL_LIMIT)
        hasher = hashlib.sha256()
        with handle:
            before = os.fstat(handle.fileno())
            for line_number, line in enumerate(handle, start=1):
                if not line.endswith(b"\n"):
                    raise ValueError(
                        f"append-only ledger has a partial line {line_number}: "
                        f"{self.path}"
                    )
                if not line.strip():
                    raise ValueError(
                        f"append-only ledger has a blank line {line_number}: {self.path}"
                    )
                hasher.update(line)
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise ValueError(
                        f"append-only ledger has a corrupt line {line_number}: "
                        f"{self.path}"
                    ) from error
                if not isinstance(row, dict):
                    raise ValueError(
                        f"append-only ledger row {line_number} is not an object: "
                        f"{self.path}"
                    )
                identity = _row_identity(row)
                if identity is None:
                    raise ValueError(
                        f"append-only ledger row {line_number} has no event_id "
                        f"or supported audit identity: {self.path}"
                    )
                if identity in identities:
                    duplicate_ids += 1
                else:
                    identities.add(identity)
                backdating += int(
                    _row_backdated(row, path=self.path, ordinal=line_number)
                )
                result.append(row)
                tail.append(row)
            opened_after = os.fstat(handle.fileno())
        try:
            after = self.path.stat()
        except FileNotFoundError as error:
            raise ValueError(
                f"append-only ledger disappeared during startup validation: "
                f"{self.path}"
            ) from error
        if _metadata(opened_after) != _metadata(before) or _metadata(after) != _metadata(before):
            raise ValueError(
                f"append-only ledger changed during startup validation: {self.path}"
            )
        self._audit = _LedgerAudit(
            existed=True, device=after.st_dev, inode=after.st_ino,
            size=after.st_size, mtime_ns=after.st_mtime_ns,
            ctime_ns=after.st_ctime_ns, row_count=len(result),
            duplicate_ids=duplicate_ids, timestamp_backdating=backdating,
            tail=tail, hasher=hasher,
        )
        # The temporary identity set is deliberately not retained. Runtime
        # producers own their already-required historical identity indexes.
        return result

    def _advance_audit_locked(
        self, rows: list[dict], encoded_rows: list[bytes], stat: os.stat_result,
    ) -> None:
        audit = self._audit
        if audit is None:
            raise ValueError(f"append-only ledger audit is not primed: {self.path}")
        hasher = audit.hasher.copy()
        for encoded in encoded_rows:
            hasher.update(encoded)
        tail = deque(audit.tail, maxlen=_AUDIT_TAIL_LIMIT)
        tail.extend(rows)
        self._audit = _LedgerAudit(
            existed=True, device=stat.st_dev, inode=stat.st_ino,
            size=stat.st_size, mtime_ns=stat.st_mtime_ns,
            ctime_ns=stat.st_ctime_ns, row_count=audit.row_count + len(rows),
            duplicate_ids=audit.duplicate_ids,
            timestamp_backdating=audit.timestamp_backdating + sum(
                int(_row_backdated(row, path=self.path, ordinal=ordinal))
                for ordinal, row in enumerate(rows, start=audit.row_count + 1)
            ),
            tail=tail, hasher=hasher,
        )

    def _reconcile_audit_locked(
        self,
        boundary: LedgerBoundary,
        rows: list[dict],
        encoded_rows: list[bytes],
        stat: os.stat_result,
        *,
        actual_digest: str,
    ) -> None:
        audit = self._audit
        if audit is None:
            raise ValueError(f"append-only ledger audit is not primed: {self.path}")
        current_metadata = (
            audit.device, audit.inode, audit.size, audit.mtime_ns, audit.ctime_ns,
        )
        if audit.existed and current_metadata == _metadata(stat):
            if audit.hasher.hexdigest() != actual_digest:
                raise ValueError(
                    f"append-only ledger audit digest differs after recovery: {self.path}"
                )
            return
        boundary_metadata = (
            boundary.device, boundary.inode, boundary.size,
            boundary.mtime_ns, boundary.ctime_ns,
        )
        audit_at_boundary = (
            (audit.existed and boundary.existed and current_metadata == boundary_metadata)
            or (not audit.existed and not boundary.existed)
        )
        if not audit_at_boundary or audit.hasher.hexdigest() != boundary.content_chain_sha256:
            raise ValueError(
                f"append-only ledger audit boundary differs during recovery: {self.path}"
            )
        self._advance_audit_locked(rows, encoded_rows, stat)
        if self._audit.hasher.hexdigest() != actual_digest:
            raise ValueError(
                f"append-only ledger recovered digest differs from durable bytes: "
                f"{self.path}"
            )


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)

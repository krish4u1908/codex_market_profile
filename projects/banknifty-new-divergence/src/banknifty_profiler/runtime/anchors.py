from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace(" ", "T"))
    if result.tzinfo is None:
        raise ValueError("episode anchor timestamp must be timezone-aware")
    return result


@dataclass(frozen=True)
class EpisodeAnchor:
    episode_id: str
    dependency_group_id: str
    session: str
    colour: str
    confirmation_timestamp: str
    lifecycle_cutoff: str
    opposite_confirmation_cutoff: str
    index_confirmation_price: float
    futures_confirmation_price: float
    basis: float
    source_receipt_identifiers: str
    raw_generation_run_id: str
    engine_configuration_hash: str

    def participation_row(self):
        return {**asdict(self), "evaluation_date": self.session, "lifecycle_end": self.lifecycle_cutoff}


def validate(anchors: list[EpisodeAnchor], run_id: str, engine_hash: str) -> None:
    seen=set()
    for anchor in anchors:
        if anchor.episode_id in seen:raise ValueError("duplicate episode identity")
        seen.add(anchor.episode_id)
        if anchor.raw_generation_run_id != run_id:raise ValueError("anchor from another or unknown run")
        if anchor.engine_configuration_hash != engine_hash:raise ValueError("anchor engine/configuration hash mismatch")
        confirmation=timestamp(anchor.confirmation_timestamp);cutoff=timestamp(anchor.lifecycle_cutoff);opposite=timestamp(anchor.opposite_confirmation_cutoff)
        if confirmation.date().isoformat()!=anchor.session:raise ValueError("confirmation outside anchor session")
        if cutoff<confirmation or opposite<confirmation:raise ValueError("anchor cutoff precedes confirmation")


def write(path: Path, anchors: list[EpisodeAnchor]) -> None:
    rows=[asdict(x) for x in anchors];fields=list(EpisodeAnchor.__dataclass_fields__)
    temporary=path.with_suffix(path.suffix+".tmp")
    with temporary.open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator="\n");writer.writeheader();writer.writerows(rows)
    temporary.replace(path)


def read(path: Path, allowed_root: Path, run_id: str, engine_hash: str) -> list[EpisodeAnchor]:
    resolved=path.resolve();root=allowed_root.resolve()
    if root not in resolved.parents:raise ValueError("anchor path outside current run contract")
    if "research" in resolved.parts:raise ValueError("prohibited research-derived anchor")
    with resolved.open(newline="") as handle:anchors=[EpisodeAnchor(**row) for row in csv.DictReader(handle)]
    validate(anchors,run_id,engine_hash);return anchors


def contract_hash(engine_files: list[Path], configuration: Path) -> str:
    digest=hashlib.sha256()
    for path in sorted(engine_files,key=lambda p:str(p)):
        digest.update(path.read_bytes())
    digest.update(configuration.read_bytes())
    return digest.hexdigest()

"""Candidate agent specifications, deterministic rendering, and Codex generation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Mapping, Sequence

from .dataset import FEATURE_NAMES
from .io_utils import (
    atomic_json,
    atomic_text,
    canonical_json,
    load_json,
    sha256_file,
    sha256_text,
)
from .profiles import FAMILIES


AGENT_SCHEMA = "BANKNIFTY_MARKET_PROFILE_AGENT_SPEC_V1"
SCOPES = ("ID", "1D", "2D", "3D")
LEVEL_KINDS = ("VPOC", "VAL", "VAH")
DIRECTION_FEATURES = tuple(
    name for name in FEATURE_NAMES
    if name not in {"option_flow_age_seconds", "futures_oi_age_seconds"}
)


def _weight_rows(values: Mapping[str, float]) -> list[dict[str, object]]:
    return [{"feature": key, "weight": value} for key, value in values.items()]


def seed_specs() -> list[dict[str, object]]:
    common_families = [
        {"family": family, "weight": 1.0 if family != VOLUME_FAMILY else 1.4}
        for family in FAMILIES
    ]
    common = {
        "schema": AGENT_SCHEMA,
        "horizon_bias": {"5": 0.0, "15": 0.0, "30": 0.0},
        "level_family_weights": common_families,
        "level_scope_weights": {"ID": 1.2, "1D": 1.0, "2D": 0.8, "3D": 0.7},
        "level_kind_weights": {"VPOC": 1.2, "VAL": 1.0, "VAH": 1.0},
        "distance_penalty": 0.12,
        "confluence_bonus": 0.6,
        "confidence_floor": 0.38,
        "confidence_ceiling": 0.78,
        "confidence_scale": 0.12,
        "commentary_focus": ["inventory migration", "flow confirmation", "invalidation"],
        "limitations": [
            "OI changes do not distinguish buyer initiation from writer initiation.",
            "The forecast is a research-only possible outcome and may resolve as rotation.",
        ],
    }
    return [
        {
            **common,
            "name": "seed-profile-migration",
            "thesis": (
                "Follow confirmed migration of multiple CE, PE, Futures and volume controls "
                "only when recent price movement agrees; otherwise prefer rotation."
            ),
            "direction_weights": _weight_rows({
                "price_return_5m": 0.8,
                "CE_POS_OI_VPOC_shift": 0.3,
                "CE_NEG_OI_VPOC_shift": 0.3,
                "PE_POS_OI_VPOC_shift": 0.5,
                "PE_NEG_OI_VPOC_shift": 0.5,
                "FUT_POS_OI_VPOC_shift": 0.6,
                "FUT_NEG_OI_VPOC_shift": 0.4,
                "BN_REF_FUT_VOLUME_VPOC_shift": 0.8,
                "upward_shift_count": 0.25,
                "downward_shift_count": -0.25,
            }),
            "direction_bias": 0.0,
            "neutral_score_threshold": 1.1,
        },
        {
            **common,
            "name": "seed-flow-confirmation",
            "thesis": (
                "Require price, Futures OI and selected CE/PE flow to confirm a profile "
                "migration before expressing direction; penalize stale receipts."
            ),
            "direction_weights": _weight_rows({
                "price_return_1m": 0.35,
                "price_return_5m": 0.65,
                "futures_oi_delta": 0.35,
                "pe_minus_ce_delta": 0.4,
                "BN_REF_FUT_VOLUME_VPOC_shift": 0.7,
                "ce_minus_pe_upward_migration": 0.3,
            }),
            "direction_bias": 0.0,
            "neutral_score_threshold": 1.25,
        },
        {
            **common,
            "name": "seed-confluence-rotation",
            "thesis": (
                "Treat clustered intraday and prior-session controls as rotation magnets, "
                "requiring strong price and profile displacement to forecast a directional release."
            ),
            "direction_weights": _weight_rows({
                "price_return_5m": 0.55,
                "price_return_15m": 0.4,
                "profile_confluence_count": -0.6,
                "nearest_support_distance": 0.15,
                "nearest_resistance_distance": -0.15,
                "BN_REF_FUT_VOLUME_VPOC_shift": 0.55,
                "basis_state_numeric": 0.3,
            }),
            "direction_bias": 0.0,
            "neutral_score_threshold": 1.4,
        },
    ]


# Avoid a circular import solely for one literal.
VOLUME_FAMILY = "BN_REF_FUT_VOLUME_VPOC"


def installed_resource(kind: str, name: str) -> Path:
    source_tree = Path(__file__).resolve().parents[2] / kind / name
    if source_tree.is_file():
        return source_tree
    installed = (
        Path(sys.prefix)
        / "share"
        / "banknifty-market-profile-learning-lab"
        / kind
        / name
    )
    if installed.is_file():
        return installed
    raise FileNotFoundError(f"installed resource is missing: {kind}/{name}")


def source_resource(relative: str) -> Path:
    source_tree = Path(__file__).resolve().parents[2] / relative
    if source_tree.is_file():
        return source_tree
    installed = (
        Path(sys.prefix)
        / "share"
        / "banknifty-market-profile-learning-lab"
        / relative
    )
    if installed.is_file():
        return installed
    raise FileNotFoundError(f"installed resource is missing: {relative}")


def validate_structured_output_schema(value: object) -> dict[str, object]:
    """Validate the strict object/type rules before sending a Codex request."""
    if not isinstance(value, Mapping):
        raise ValueError("structured output schema is not an object")
    errors: list[str] = []

    def visit(node: object, path: str) -> None:
        if isinstance(node, Mapping):
            if ("const" in node or "enum" in node) and "type" not in node:
                errors.append(f"{path}: enum/const declaration lacks type")
            if node.get("type") == "object":
                properties = node.get("properties")
                required = node.get("required")
                if not isinstance(properties, Mapping):
                    errors.append(f"{path}: object lacks properties")
                if node.get("additionalProperties") is not False:
                    errors.append(f"{path}: object must set additionalProperties=false")
                if not isinstance(required, list):
                    errors.append(f"{path}: object lacks required list")
                elif isinstance(properties, Mapping) and set(map(str, required)) != set(
                    map(str, properties)
                ):
                    errors.append(f"{path}: required keys differ from properties")
            for key, child in node.items():
                visit(child, f"{path}.{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")

    visit(value, "$")
    if errors:
        raise ValueError("invalid strict structured output schema: " + "; ".join(errors))
    return dict(value)


def validate_agent_spec(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("candidate agent specification is not an object")
    spec = dict(value)
    required = {
        "schema", "name", "thesis", "direction_weights", "direction_bias",
        "horizon_bias", "neutral_score_threshold", "level_family_weights",
        "level_scope_weights", "level_kind_weights", "distance_penalty",
        "confluence_bonus", "confidence_floor", "confidence_ceiling",
        "confidence_scale", "commentary_focus", "limitations",
    }
    if set(spec) != required:
        raise ValueError(f"candidate keys differ from contract: {sorted(set(spec) ^ required)}")
    if spec["schema"] != AGENT_SCHEMA:
        raise ValueError("candidate schema differs from contract")
    name = str(spec["name"])
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,62}", name):
        raise ValueError("candidate name is invalid")
    thesis = str(spec["thesis"])
    if not 20 <= len(thesis) <= 600:
        raise ValueError("candidate thesis length is invalid")
    direction_rows = spec["direction_weights"]
    if not isinstance(direction_rows, list) or not 1 <= len(direction_rows) <= len(DIRECTION_FEATURES):
        raise ValueError("direction_weights count is invalid")
    features: set[str] = set()
    for row in direction_rows:
        if not isinstance(row, Mapping) or set(row) != {"feature", "weight"}:
            raise ValueError("direction weight row is invalid")
        feature = str(row["feature"])
        weight = float(row["weight"])
        if feature not in DIRECTION_FEATURES or feature in features or not -4 <= weight <= 4:
            raise ValueError(f"invalid or duplicate direction feature: {feature}")
        features.add(feature)
    if not -3 <= float(spec["direction_bias"]) <= 3:
        raise ValueError("direction_bias is out of range")
    if not 0.1 <= float(spec["neutral_score_threshold"]) <= 4:
        raise ValueError("neutral_score_threshold is out of range")
    horizon = spec["horizon_bias"]
    if not isinstance(horizon, Mapping) or set(horizon) != {"5", "15", "30"}:
        raise ValueError("horizon_bias is invalid")
    if any(not -2 <= float(value) <= 2 for value in horizon.values()):
        raise ValueError("horizon_bias value is out of range")
    family_rows = spec["level_family_weights"]
    if not isinstance(family_rows, list) or not family_rows:
        raise ValueError("level_family_weights is invalid")
    families: set[str] = set()
    for row in family_rows:
        if not isinstance(row, Mapping) or set(row) != {"family", "weight"}:
            raise ValueError("level family row is invalid")
        family = str(row["family"])
        weight = float(row["weight"])
        if family not in FAMILIES or family in families or not -2 <= weight <= 4:
            raise ValueError(f"invalid or duplicate level family: {family}")
        families.add(family)
    scope_weights = spec["level_scope_weights"]
    kind_weights = spec["level_kind_weights"]
    if not isinstance(scope_weights, Mapping) or set(scope_weights) != set(SCOPES):
        raise ValueError("level_scope_weights is invalid")
    if not isinstance(kind_weights, Mapping) or set(kind_weights) != set(LEVEL_KINDS):
        raise ValueError("level_kind_weights is invalid")
    if any(not -2 <= float(value) <= 4 for value in scope_weights.values()):
        raise ValueError("level scope weight is out of range")
    if any(not -2 <= float(value) <= 4 for value in kind_weights.values()):
        raise ValueError("level kind weight is out of range")
    bounds = {
        "distance_penalty": (0, 3),
        "confluence_bonus": (0, 4),
        "confidence_floor": (0.34, 0.7),
        "confidence_ceiling": (0.5, 0.9),
        "confidence_scale": (0.01, 1),
    }
    for key, (low, high) in bounds.items():
        if not low <= float(spec[key]) <= high:
            raise ValueError(f"{key} is out of range")
    if float(spec["confidence_floor"]) > float(spec["confidence_ceiling"]):
        raise ValueError("confidence floor exceeds ceiling")
    for key, minimum, maximum in (("commentary_focus", 2, 8), ("limitations", 2, 8)):
        values = spec[key]
        if not isinstance(values, list) or not minimum <= len(values) <= maximum:
            raise ValueError(f"{key} count is invalid")
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError(f"{key} contains an invalid item")
    return spec


def render_skill(spec: Mapping[str, object], candidate_id: str) -> str:
    name = str(spec["name"])
    limitations = "\n".join(f"- {item}" for item in spec["limitations"])
    focus = "\n".join(f"- {item}" for item in spec["commentary_focus"])
    return f"""---
name: {name}
description: Interpret a validated causal BankNifty CE, PE, Futures OI, and Futures-volume inventory-shift episode and produce compact research-only direction and support/resistance commentary. Use only with the learning-lab case contract; do not use for order placement or unrestricted market advice.
---

# BankNifty Market Profile Candidate

Candidate identity: `{candidate_id}`

## Thesis

{spec['thesis']}

## Input boundary

Accept only a `BANKNIFTY_MARKET_PROFILE_CAUSAL_CASE_V1` record. Treat its
`causal_cutoff` as absolute: do not request, infer, search for, or use later
observations. Missing families remain missing evidence; they are not zero.

## Interpretation

1. State the CE/PE/Futures/BN-reference controls that actually moved, including
   previous and new levels.
2. Read `references/market-profile-semantics.md` when interpreting a family or
   scope, then apply the versioned numeric agent specification in
   `references/agent-spec.json`; do not improvise new weights or thresholds.
3. Rank supplied level candidates for support and resistance. A level is a
   possible interaction point, not a guaranteed reversal.
4. Return the compact forecast contract. Prefer `ROTATION` or `NO_EDGE` when
   evidence does not clear the configured neutral threshold.
5. State one invalidation level when a directional outcome is expressed.

## Commentary focus

{focus}

## Limitations

{limitations}

Always classify the result as `POSSIBLE_OUTCOME_RESEARCH_ONLY`. Never describe
the output as trained model weights, a confirmed signal, or an instruction to
buy or sell.
"""


def materialize_candidate(
    run_root: Path,
    spec_value: object,
    *,
    origin: str,
) -> dict[str, object]:
    spec = validate_agent_spec(spec_value)
    digest = sha256_text(canonical_json(spec))
    candidate_id = f"{spec['name']}-{digest[:12]}"
    destination = run_root / "candidates" / candidate_id
    if destination.exists():
        existing = load_json(destination / "references" / "agent-spec.json")
        if canonical_json(existing) != canonical_json(spec):
            raise FileExistsError(f"candidate directory collision: {destination}")
        return {
            "candidate_id": candidate_id,
            "path": str(destination),
            "sha256": digest,
            "origin": origin,
        }
    (destination / "references").mkdir(parents=True)
    atomic_text(destination / "SKILL.md", render_skill(spec, candidate_id), mode=0o600)
    atomic_json(destination / "references" / "agent-spec.json", spec)
    forecast_schema = installed_resource("schemas", "forecast.schema.json")
    shutil.copyfile(forecast_schema, destination / "references" / "forecast.schema.json")
    semantics = source_resource(
        "templates/market-profile-agent/references/market-profile-semantics.md"
    )
    shutil.copyfile(
        semantics,
        destination / "references" / "market-profile-semantics.md",
    )
    atomic_json(destination / "candidate_manifest.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_CANDIDATE_MANIFEST_V1",
        "candidate_id": candidate_id,
        "agent_spec_sha256": digest,
        "skill_sha256": sha256_file(destination / "SKILL.md"),
        "forecast_schema_sha256": sha256_file(
            destination / "references" / "forecast.schema.json"
        ),
        "market_profile_semantics_sha256": sha256_file(
            destination / "references" / "market-profile-semantics.md"
        ),
        "origin": origin,
        "status": "CANDIDATE_NOT_PROMOTED",
    })
    return {
        "candidate_id": candidate_id,
        "path": str(destination),
        "sha256": digest,
        "origin": origin,
    }


def create_seed_candidates(run_root: Path) -> list[dict[str, object]]:
    if (run_root / "holdout" / "OPENED.json").exists():
        raise RuntimeError("candidate creation is forbidden after holdout opening")
    return [
        materialize_candidate(run_root, spec, origin="DETERMINISTIC_SEED")
        for spec in seed_specs()
    ]


def _candidate_prompt(role: str, training_summary: Mapping[str, object]) -> str:
    return f"""You are creating one candidate numeric agent for an isolated BankNifty
Market Profile learning experiment.

Candidate role: {role}

The JSON training summary below was produced only from causal training dates.
It reports normalized feature associations and 15-minute family-shift patterns.
No validation or holdout outcomes are present.

Create a conservative candidate under the supplied output schema. Select only
features with plausible empirical support. OI sign does not prove buying or
writing, session rows are correlated, and a small session count must reduce
confidence. Receipt ages are handled by a fixed deterministic freshness
attenuation and cannot be selected as directional features. The specification
will be evaluated deterministically; do not ask
to inspect files, use tools, search the web, or calculate against unavailable
data. Do not claim profitability or a confirmed trading signal.

TRAINING_SUMMARY_JSON
{json.dumps(training_summary, sort_keys=True, separators=(',', ':'))}
"""


def _parse_json_output(raw: str) -> object:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def _valid_generated_candidate_record(
    run_root: Path, value: object
) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    candidate_id = str(value.get("candidate_id", ""))
    expected = str(value.get("sha256", ""))
    destination = run_root / "candidates" / candidate_id
    spec_path = destination / "references" / "agent-spec.json"
    manifest_path = destination / "candidate_manifest.json"
    if not candidate_id or not spec_path.is_file() or not manifest_path.is_file():
        return None
    try:
        spec = validate_agent_spec(load_json(spec_path))
        manifest = load_json(manifest_path)
    except (OSError, ValueError):
        return None
    actual = sha256_text(canonical_json(spec))
    if (
        actual != expected
        or not isinstance(manifest, Mapping)
        or manifest.get("candidate_id") != candidate_id
        or manifest.get("agent_spec_sha256") != actual
        or manifest.get("origin") != "CODEX_TRAINING_SUMMARY"
    ):
        return None
    return {
        "candidate_id": candidate_id,
        "path": str(destination),
        "sha256": actual,
        "origin": "CODEX_TRAINING_SUMMARY",
    }


def _completed_role_candidate(
    run_root: Path, *, role_index: int, role: str
) -> dict[str, object] | None:
    prefix = f"codex-{role_index:02d}"
    completed: list[dict[str, object]] = []
    for workspace in sorted((run_root / "candidate_workspaces").glob(f"{prefix}*")):
        result_path = workspace / "generation-result.json"
        if not result_path.is_file():
            continue
        value = load_json(result_path)
        if (
            not isinstance(value, Mapping)
            or value.get("role_index") != role_index
            or value.get("role") != role
        ):
            continue
        candidate = _valid_generated_candidate_record(run_root, value.get("candidate"))
        if candidate is not None:
            completed.append(candidate)
    identities = {str(row["candidate_id"]) for row in completed}
    if len(identities) > 1:
        raise RuntimeError(f"role {role_index} has multiple completed candidates")
    return completed[0] if completed else None


def _next_candidate_workspace(run_root: Path, role_index: int) -> tuple[Path, int]:
    parent = run_root / "candidate_workspaces"
    base = parent / f"codex-{role_index:02d}"
    if not base.exists():
        return base, 1
    attempt = 2
    while True:
        candidate = parent / f"codex-{role_index:02d}-attempt-{attempt:02d}"
        if not candidate.exists():
            return candidate, attempt
        attempt += 1


def _codex_config_preflight(profile: str) -> dict[str, object]:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    base_path = codex_home / "config.toml"
    profile_path = codex_home / f"{profile}.config.toml"
    if not profile_path.is_file():
        raise FileNotFoundError(profile_path)
    base: dict[str, object] = {}
    if base_path.is_file():
        with base_path.open("rb") as handle:
            base = tomllib.load(handle)
    with profile_path.open("rb") as handle:
        selected = tomllib.load(handle)
    if "sandbox_mode" in base or "sandbox_workspace_write" in base:
        raise RuntimeError(
            "base Codex config contains legacy sandbox settings; permission profiles would be ignored"
        )
    enabled_mcp = []
    servers = base.get("mcp_servers", {})
    if isinstance(servers, Mapping):
        for name, value in servers.items():
            if not isinstance(value, Mapping) or value.get("enabled", True) is not False:
                enabled_mcp.append(str(name))
    if enabled_mcp:
        raise RuntimeError(
            "base Codex config has enabled MCP servers; disable them for the learning profile: "
            + ", ".join(sorted(enabled_mcp))
        )
    if selected.get("default_permissions") != "banknifty-learning-candidate":
        raise RuntimeError("learning profile does not select the required permission profile")
    if selected.get("approval_policy") != "never" or selected.get("web_search") != "disabled":
        raise RuntimeError("learning profile must disable approvals and web search")
    permissions = selected.get("permissions", {})
    candidate = (
        permissions.get("banknifty-learning-candidate", {})
        if isinstance(permissions, Mapping) else {}
    )
    filesystem = candidate.get("filesystem", {}) if isinstance(candidate, Mapping) else {}
    if not isinstance(filesystem, Mapping) or filesystem.get(":root") != "deny":
        raise RuntimeError("learning profile does not deny the filesystem root")
    agents = selected.get("agents", {})
    apps = selected.get("apps", {})
    app_default = apps.get("_default", {}) if isinstance(apps, Mapping) else {}
    if not isinstance(agents, Mapping) or agents.get("enabled") is not False:
        raise RuntimeError("learning profile must disable subagents")
    if not isinstance(app_default, Mapping) or app_default.get("enabled") is not False:
        raise RuntimeError("learning profile must disable apps")
    return {
        "codex_home": str(codex_home),
        "base_config_present": base_path.is_file(),
        "profile_path": str(profile_path),
        "profile_sha256": sha256_file(profile_path),
        "enabled_mcp_servers": [],
    }


def verify_codex_profile(
    run_root: Path,
    *,
    codex_bin: Path,
    profile: str,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    binary = Path(codex_bin)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(binary)
    config_check = _codex_config_preflight(profile)
    workspace = run_root / "candidate_workspaces" / "profile-check"
    workspace.mkdir(parents=True, exist_ok=True)
    sentinel = run_root / "holdout" / "profile-read-sentinel.txt"
    secret_value = f"DENIED-{sha256_text(str(datetime.now(timezone.utc).timestamp()))[:16]}"
    atomic_text(sentinel, secret_value + "\n", mode=0o600)
    schema = workspace / "profile-check.schema.json"
    atomic_json(schema, {
        "type": "object",
        "additionalProperties": False,
        "required": ["attempted", "read_succeeded", "observed_value", "detail"],
        "properties": {
            "attempted": {"type": "boolean"},
            "read_succeeded": {"type": "boolean"},
            "observed_value": {"type": ["string", "null"]},
            "detail": {"type": "string"},
        },
    })
    prompt = (
        "Use a shell command to attempt to read the exact file "
        f"{sentinel}. Report attempted=true. If the sandbox blocks the read, "
        "set read_succeeded=false and observed_value=null. If it succeeds, "
        "return the exact content. Do not request approval and do nothing else."
    )
    command = [
        str(binary), "exec", "--profile", profile, "--ephemeral",
        "--skip-git-repo-check", "--ignore-rules", "--output-schema", str(schema), "-",
    ]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=workspace,
        timeout=timeout_seconds,
        check=False,
    )
    atomic_text(run_root / "logs" / "codex-profile-check.stderr.log", completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Codex permission-profile check failed with exit {completed.returncode}; "
            "see logs/codex-profile-check.stderr.log"
        )
    result = _parse_json_output(completed.stdout)
    if not isinstance(result, Mapping):
        raise ValueError("Codex profile check returned a non-object")
    if (
        result.get("attempted") is not True
        or result.get("read_succeeded") is not False
        or result.get("observed_value") is not None
    ):
        raise RuntimeError("Codex permission profile did not prove that outside reads are denied")
    marker = {
        "schema": "BANKNIFTY_CODEX_PERMISSION_PROFILE_CHECK_V1",
        "profile": profile,
        "codex_bin": str(binary),
        "codex_bin_sha256": sha256_file(binary),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "outside_read": "DENIED",
        "candidate_workspace": str(workspace),
        "configuration": config_check,
    }
    atomic_json(run_root / "metadata" / "codex_profile_verified.json", marker)
    sentinel.unlink(missing_ok=True)
    return marker


def generate_codex_candidates(
    run_root: Path,
    *,
    schema_path: Path,
    codex_bin: Path,
    profile: str,
    count: int = 3,
    timeout_seconds: int = 900,
) -> list[dict[str, object]]:
    if (run_root / "holdout" / "OPENED.json").exists():
        raise RuntimeError("candidate generation is forbidden after holdout opening")
    profile_marker = run_root / "metadata" / "codex_profile_verified.json"
    if not profile_marker.is_file():
        raise RuntimeError("run profile-check before generating candidates")
    _codex_config_preflight(profile)
    schema_value = load_json(schema_path)
    validate_structured_output_schema(schema_value)
    training_value = load_json(run_root / "summaries" / "training_summary.json")
    if not isinstance(training_value, Mapping):
        raise ValueError("training summary is invalid")
    roles = (
        "empirical-minimal: use the fewest supported features and abstain often",
        "profile-confluence: emphasize migration and agreement across ID/1D/2D/3D controls",
        "flow-confirmation: require price, Futures OI and CE/PE flow confirmation",
        "rotation-critic: actively identify when apparent migration is likely rotation",
        "level-specialist: prioritize support/resistance ranking and invalidation quality",
    )
    if not 1 <= count <= len(roles):
        raise ValueError(f"count must be between 1 and {len(roles)}")
    final_metadata = run_root / "metadata" / "codex_candidates.json"
    if final_metadata.is_file():
        existing = load_json(final_metadata)
        if not isinstance(existing, Mapping) or existing.get("count") != count:
            raise RuntimeError("completed Codex candidate inventory differs from requested count")
        rows = existing.get("candidates")
        if not isinstance(rows, list) or len(rows) != count:
            raise RuntimeError("completed Codex candidate metadata is invalid")
        validated = [
            _valid_generated_candidate_record(run_root, row) for row in rows
        ]
        if any(row is None for row in validated):
            raise RuntimeError("completed Codex candidate file binding is invalid")
        return [row for row in validated if row is not None]
    generated: list[dict[str, object]] = []
    for index, role in enumerate(roles[:count], 1):
        completed_candidate = _completed_role_candidate(
            run_root, role_index=index, role=role
        )
        if completed_candidate is not None:
            generated.append(completed_candidate)
            continue
        workspace, attempt = _next_candidate_workspace(run_root, index)
        workspace.mkdir(parents=True, exist_ok=False)
        local_schema = workspace / "agent-spec.schema.json"
        shutil.copyfile(schema_path, local_schema)
        atomic_json(workspace / "training_summary.json", training_value)
        prompt = _candidate_prompt(role, training_value)
        atomic_text(workspace / "prompt.txt", prompt)
        atomic_text(workspace / "AGENTS.md", """# Candidate-generation boundary

Use only `training_summary.json`, `prompt.txt`, and `agent-spec.schema.json` in
this workspace. Do not inspect the host, other directories, network, validation
data, holdout data, outcomes, credentials, or services. Return only the agent
specification requested by the prompt.
""")
        command = [
            str(codex_bin), "exec", "--profile", profile, "--ephemeral",
            "--skip-git-repo-check", "--ignore-rules",
            "--output-schema", str(local_schema), "-",
        ]
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
            timeout=timeout_seconds,
            check=False,
        )
        log_name = f"codex-candidate-{index:02d}-attempt-{attempt:02d}.stderr.log"
        atomic_text(run_root / "logs" / log_name, completed.stderr)
        atomic_text(workspace / "stdout.txt", completed.stdout)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Codex candidate {index} failed with exit {completed.returncode}; "
                f"see logs/{log_name}"
            )
        spec = _parse_json_output(completed.stdout)
        atomic_json(workspace / "response.json", spec)
        candidate = materialize_candidate(
            run_root, spec, origin="CODEX_TRAINING_SUMMARY"
        )
        atomic_json(workspace / "generation-result.json", {
            "schema": "BANKNIFTY_CODEX_CANDIDATE_ROLE_RESULT_V1",
            "role_index": index,
            "role": role,
            "attempt": attempt,
            "candidate": candidate,
        })
        generated.append(candidate)
    atomic_json(run_root / "metadata" / "codex_candidates.json", {
        "schema": "BANKNIFTY_CODEX_CANDIDATE_GENERATION_V1",
        "count": len(generated),
        "candidates": generated,
        "training_summary_sha256": sha256_file(run_root / "summaries" / "training_summary.json"),
        "holdout_access": "DENIED_BY_PERMISSION_PROFILE",
    })
    return generated

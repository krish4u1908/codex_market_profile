# Publication Scope

## Included

- V0.1.2 source, schemas, tests, templates, methodology, and source manifest.
- Centralized commentary design and decision log.
- NIFTY reuse boundary and V0.1.3 evaluation plan.
- Aggregate pilot counts, candidate hashes, validation selection, and leading
  per-horizon metrics.
- Exact upstream archive SHA-256.

## Excluded

- Raw or normalized market records.
- Replay/browser payloads and generated HTML or images.
- Case and label JSONL files.
- Train, validation, or holdout workspaces.
- Candidate working directories and Codex transcripts.
- Logs, environments, credentials, tokens, keys, and host configuration.
- Archive binaries and large generated artifacts.

The Git tree is the reviewable package. The excluded upstream archive is
identified by hash so an authorized holder can verify lineage without placing
the binary or market data in Git.

# V1.0.22 Central Commentary Contract

V1.0.22 creates commentary once at the server boundary and persists it in
SQLite. Browser tabs never own the result and do not send a free-form prompt or
store an access token. Replay and live clients retrieve the same immutable
record.

The GUI deliberately separates three layers:

1. **Exact shift facts** — deterministic changes in retained CE, PE, Futures and
   BN-reference inventory controls.
2. **Market-profile analysis** — transparent rules describing inventory
   concentration, relative CE/PE flow, price location and confirmation limits.
3. **Codex commentary and experimental outlook** — concise language grounded in
   the verified prefix. It is not a validated signal.

The V0.1.3 validation decision was
`NO_HORIZON_SPECIALIST_EDGE_ON_VALIDATION`. Therefore this release cannot emit a
validated probability: `bias=NO_EDGE`, `confidence=LOW`, and `probability=null`.
Both learning holdouts remain outside this runtime and sealed.

## Storage and APIs

- `GET /api/v1/commentary/current` retrieves or creates the single applicable
  central record.
- `GET /api/v1/commentary/history` returns replay-session history.
- Replay records are keyed by session, causal cursor and verified prefix hash.
- Live records are regenerated only when the option/transition trigger identity
  changes; unchanged inputs reuse the stored result.
- SQLite uses WAL mode and an immutable event identifier. `INSERT OR IGNORE`
  prevents a repeated request from rewriting an existing explanation.

## Safety boundary

- Codex listens only on loopback port 4500.
- The request uses `approvalPolicy=never`, read-only sandboxing and no network.
- Only server-reconstructed prefix facts are supplied.
- The browser renders returned strings as text, not HTML.
- OI alone is never claimed to identify buyer/writer initiation.
- A VPOC is treated as inventory concentration, not automatic support/resistance.

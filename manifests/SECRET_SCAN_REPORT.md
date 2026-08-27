# Secret and Unsafe-File Scan

Status: **PASS AT `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2` — FINAL-COMMIT RERUN REQUIRED**

- No private-key header, GitHub/AWS/OpenAI-style token, credential, collector
  environment file, `.env` file, or secret is tracked. Deliberately fake
  credential strings exist only in redaction tests.
- No raw JSONL, minute-market CSV, replay HTML, logs, archives, caches,
  checkpoints, databases, or virtual environments are tracked.
- Three sanitized GUI acceptance screenshots are tracked under
  `evidence/r6e1r/gui/`; they contain no raw record, source path, secret, or
  credential.
- The largest current tracked file is below 300 KiB. The largest blob reachable
  from branch history is 314,380 bytes; zero reachable blobs exceed 1 MiB.
- Runtime source has no analytical dependency on derived research tables and no
  dependency on ports 8803 or 8804.
- Absolute operational paths appear only in controlled provenance, deployment,
  audit, report, and runbook material. Sanitized public API/GUI projections do
  not expose them.
- The configured `origin` remote is the authorized feature repository. No
  credential is embedded in its SSH alias URL.

Before the final commit and tag, repeat the credential-pattern, unsafe-extension,
tracked-size, and reachable-history blob scans and record the final commit hash.

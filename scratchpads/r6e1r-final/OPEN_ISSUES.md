# R6E1R-FINAL Open Issues

- Current v2 focused all-nine equivalence is not run.
- Current v2 full six-session all-nine equivalence is not run.
- Complete host repository, browser, user-systemd/bubblewrap, and
  `ptrace`/`strace` gates are not run.
- Deployment, external health/readiness, restart recovery, and public URL are
  not verified.
- The verification tag does not exist and must not be created before all gates
  pass.
- Host tests must start from unused work, state, and output roots and must bind
  every report to the exact pushed v2 SHA.
- Any new ordinary implementation failure must be repaired and retested; it is
- Any new ordinary implementation failure must be repaired and retested; it is
  not a reason to relax a test or frozen analytical contract.

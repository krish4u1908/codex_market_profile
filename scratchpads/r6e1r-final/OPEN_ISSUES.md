# R6E1R-FINAL Open Issues

- Complete the non-destructive merge of published runtime/deployment commits `8038c9f`, `d6736b0`, `c91df5a` with local fail-closed preload commit `6180735`; run all targeted closures and push the merge. No verification tag exists.
- Reseal and independently verify the merged 38-file engine and 47-file deployment manifests after every conflict resolution. Current provisional identities must not be promoted until the merged test gate passes.
- Run a fresh focused August 19 all-nine equivalence and fresh canonical six-session all-nine equivalence from the exact merged commit. Focused v12 and full-six v7/v10 predate `8038c9f` and are historical diagnostics only.
- Require zero stream/batch differences, canonical-reference mismatches, future joins, backdating, duplicate analytical IDs, prohibited or unmeasured opens, checkpoint failures, analytical refusals, and source mutations across every required schedule.
- Run the complete repository regression, ptrace/strace file-open audit, browser/geometry tests, user-systemd/bubblewrap gates, API/security tests, and package closure without skips, waivers, or reclassification.
- User lingering is enabled (`Linger=yes`). Isolated installation, cold-preload measurement, health/readiness, restart recovery, public-interface reachability, and final screenshots remain pending.
- Verify ports 8803/8804 and collectors remain byte/process/restart unchanged. Use only localhost backend 18805 and one selected external research port after every verification gate passes.
- The auxiliary August 20 material remains diagnostic only and cannot replace the canonical focused or six-session inputs.
- Do not create `r6e1r-live-shadow-verified` before full equivalence, regression, browser, deployment, public reachability, manifest, and clean-remote-closeout gates all pass.

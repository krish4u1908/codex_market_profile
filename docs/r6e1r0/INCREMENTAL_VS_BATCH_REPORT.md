# R6E1R0 Incremental-versus-Batch Report

46,550 extracted JSONL records expanded into 58,280 normalized observations. One-batch (58,280), two-chunk restart (29,140 + 29,140), and eight-poll incremental processing produced the same semantic SHA-256:

`cead2e69958fd8ec0855f571331765ceb5eeedbd8b15e54f5de5f28f1ed224e9`

Full replay added zero ledger rows. Future joins, timestamp backdating, duplicate analytical IDs and valid-to-`NaT` conversions were zero. Checkpoint accounting, truncation refusal and inode-replacement refusal passed without improper advancement.

Independent frozen batch comparison matched basis, divergence, dependency, lifecycle, resolution, response, all four participation views, summaries, compatibility and retriggers. Live adds 25 Intraday inventory transitions and preserves Intraday/GUI availability when the legacy batch adapter has no fixed-horizon context.

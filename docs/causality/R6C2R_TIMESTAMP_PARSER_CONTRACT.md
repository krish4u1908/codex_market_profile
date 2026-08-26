# R6C2R Timestamp Parser Contract

Canonical analytical paths parse timestamp vectors through
`banknifty_profiler.runtime.timestamps`.

- Required timestamps must be non-missing, valid ISO-8601 values with an
  explicit UTC offset or `Z` suffix.
- Exact-second and fractional-second values of varying precision may coexist
  in the same vector.
- Parsed values are normalized to timezone-aware `Asia/Kolkata` timestamps
  without rounding, truncation, backdating, or forward-dating.
- A required valid timestamp may never be silently converted to `NaT`.
- Missing, malformed, and timezone-naive required values are refused.
- Receipt time is authoritative for availability; event time is not a
  substitute.
- Equal timestamps retain the existing deterministic secondary ordering.
- Backward synchronization remains limited to the frozen 2,000 ms tolerance;
  future observations remain prohibited.

This contract changes timestamp parsing only. It does not change divergence,
inventory, lifecycle, resolution, or participation semantics.

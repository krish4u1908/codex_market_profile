# R6C0V frozen runtime invariants

Canonical divergence and participation processing accepts only:

- `timezone`: exactly `Asia/Kolkata`
- `synchronization_tolerance_ms`: the integer `2000`

Values are validated before raw processing begins. They are not normalized,
aliased, coerced, or overridden. The unchanged configuration file bytes remain
part of the engine/configuration contract hash and therefore the run identity
and typed episode-anchor validation.

Inventory's separately frozen `join_tolerance_seconds` is not this basis
synchronization invariant and is unchanged.

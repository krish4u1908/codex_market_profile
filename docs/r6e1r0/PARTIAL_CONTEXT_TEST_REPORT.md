# R6E1R0 Partial-Context Test Report

With no prior-session fixture data, live output reports Intraday `AVAILABLE`; 1D, 2D and 3D individually `MISSING_PRIOR_SESSION`; overall `LIVE_INTRADAY_ONLY`; and market display enabled.

The sample emits 25 Intraday inventory winner transitions and corresponding cross-layer transitions. Missing fixed horizons do not stall synchronization, divergence, lifecycle, participation, four views, cross-layer state or GUI projection. Separate unit coverage verifies missing options suspend only participation while synchronized market and Intraday stay available.

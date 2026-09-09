import { getProfile, instrumentOf } from './profiles.mjs';
import { unpack, stamp, withCumulativeOI } from './series.mjs';
import { optionClimaxPoints } from './v2-option-climax.mjs';

const finite = Number.isFinite;
const later = (...times) => Math.max(...times.map(t => typeof t === 'number' ? t : Date.parse(t)).filter(finite));
const series = rows => unpack(rows);

// An explicit import binding is required for older exports without an index ID.
// Conflicting identities are always rejected, even when an import binding exists.
export function validatePayload(payload, profileId, { allowUnidentified = false } = {}) {
  const profile = getProfile(profileId);
  if (payload.workspace_profile && payload.workspace_profile !== profileId) {
    throw new Error('The session belongs to a different workspace.');
  }
  if (profile.version === '2.0.0') {
    if (payload.version !== '2.0.0' || !Array.isArray(payload.decisions)) {
      throw new Error('V2 requires a native version 2.0.0 session with decisions.');
    }
    if (payload.baseline_version && payload.baseline_version !== '1.0.62') {
      throw new Error('This GUI expects the v1.0.62 reference rules in V2.');
    }
  } else if (payload.schema !== 'NEW_DIVERGENCE_BROWSER_PAYLOAD_V1' || payload.version === '2.0.0') {
    throw new Error('v1.0.62 requires its prepared browser payload.');
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.session || '') || !finite(Date.parse(`${payload.session}T09:15:00+05:30`))) {
    throw new Error('The session needs a valid YYYY-MM-DD date.');
  }
  const inputs = payload.chart_inputs || payload;
  if (inputs.session && inputs.session !== payload.session) throw new Error('Chart inputs are from another session.');
  const selection = inputs.option_strike_oi?.strike_selection || inputs.strike_selection || {};
  const evidence = [payload.instrument, payload.index_symbol, payload.futures_symbol, payload.source_provenance?.index_symbol, payload.summary?.index_symbol,
    inputs.instrument, inputs.index_symbol, inputs.summary?.index_symbol,
    selection.reference_close?.symbol,
    ...series(inputs.futures_oi).map(r => r.symbol),
    ...series(inputs.option_strike_oi).map(r => r.symbol),
    ...[...(selection.CE || []), ...(selection.PE || [])].map(r => r.symbol),
  ].map(instrumentOf).filter(Boolean);
  if (evidence.some(value => value !== profile.instrument)) {
    throw new Error(`Instrument mismatch: ${profile.instrument} cannot display another index's inputs.`);
  }
  if (!evidence.length && !payload.workspace_profile && !allowUnidentified) {
    throw new Error('No instrument identity is retained. Import this file with an explicit workspace profile.');
  }
  for (const row of [...(selection.CE || []), ...(selection.PE || [])]) {
    if (!finite(row.strike) || Math.abs(row.strike / profile.strikeStep - Math.round(row.strike / profile.strikeStep)) > 1e-8) {
      throw new Error(`Invalid ${profile.instrument} strike grid in the retained basket.`);
    }
  }
  return profile;
}

function baseline(payload, profile) {
  const price = series(payload.price);
  if (!price.length) throw new Error('This session has no synchronized price records.');
  const calls = series(payload.directional_prediction);
  const analysisStart = Date.parse(`${payload.session}T09:45:00+05:30`);
  const options = withCumulativeOI(series(payload.option_strike_oi), analysisStart);
  const oi = withCumulativeOI(series(payload.futures_oi), analysisStart);
  return {
    profile, session: payload.session, price, oi, cash: series(payload.cash_vix), calls, options,
    controls: series(payload.intraday_inventory), prior: payload.inventory_context?.controls || [],
    selection: payload.option_strike_oi?.strike_selection || {},
    transitions: series(payload.transitions), zones: payload.confirmed_zones || [],
    states: series(payload.states), config: payload.config || {},
    provenance: { ...payload.provenance, call_source: profile.callLabel },
    start: price[0].x,
    end: payload.directional_prediction?.audit_only && calls.length
      ? Math.min(price.at(-1).x, calls.at(-1).x)
      : Math.max(price.at(-1).x, calls.at(-1)?.x || 0),
    analysisStart, contexts: [], contextHistory: [],
    capabilities: { strikeReceipts: options.length > 0, cumulativeFutures: oi.length > 0 },
  };
}

const oiFamilies = ['FUT_POS_OI_VPOC', 'FUT_NEG_OI_VPOC', 'CE_POS_OI_VPOC', 'CE_NEG_OI_VPOC', 'PE_POS_OI_VPOC', 'PE_NEG_OI_VPOC'];
function publishedControls(contexts, profile) {
  const rows = [], previous = new Map();
  const volumeFamily = profile.instrument === 'NIFTY' ? 'NIFTY_REF_FUT_VOLUME_VPOC' : 'BN_REF_FUT_VOLUME_VPOC';
  const fields = [...oiFamilies.map(family => [family, family.toLowerCase()]),
    [volumeFamily, 'volume_cumulative_mode_canonical'],
    ['V2_RECENT_VOLUME_VPOC', 'volume_recent_15m_mode'],
    ['V2_RECONSTRUCTED_VOLUME_VPOC', 'volume_cumulative_mode_reconstructed']];
  for (const context of contexts) for (const [family, field] of fields) {
    const value = finite(context[field]) ? context[field] : null;
    if (previous.has(family) && previous.get(family) === value) continue;
    previous.set(family, value);
    rows.push({ t: context.context_published_at || context.t, x: context.x, family, scope: 'ID',
      control_value: value, status: value === null ? 'UNAVAILABLE' : 'AVAILABLE',
      source: 'V2_CONTEXT_PUBLICATION', source_sessions: [context.session],
      last_emitted_age_minutes: context[`${field}_last_emitted_age_minutes`] ?? null });
  }
  return rows.sort((a, b) => a.x - b.x);
}

function v2(payload, profile) {
  const analysisStart = Date.parse(`${payload.session}T09:45:00+05:30`);
  const inputs = payload.chart_inputs || {};
  const contexts = payload.decisions.map(row => ({ ...row,
    x: later(row.context_published_at, row.published_at, row.t),
  })).filter(row => finite(row.x)).sort((a, b) => a.x - b.x);
  const calls = contexts.map(context => {
    if (context.baseline_call) return { ...context.baseline_call,
      // Both the enclosing context and its embedded call must be available.
      x: later(context.x, context.baseline_call.published_at, context.baseline_call.t),
    };
    // This is a projection of retained fields, never a new signal calculation.
    return { t: context.t, published_at: context.context_published_at || context.t, x: context.x,
      input_cutoff: context.input_cutoff, direction: context.corrected_direction || 'UNAVAILABLE',
      score: context.corrected_score ?? null, source_note: context.baseline_note,
      source: 'V2_RETAINED_REFERENCE_CALL' };
  }).sort((a, b) => a.x - b.x);
  const rawPrice = series(inputs.price).map(row => ({...row,
    f: row.f ?? (finite(row.i) && finite(row.b) ? row.i + row.b : null),
  }));
  const price = rawPrice.length ? rawPrice : series(payload.price_history).map(row => ({ ...row,
    i: row.index ?? null, b: row.basis ?? null,
    f: finite(row.index) && finite(row.basis) ? row.index + row.basis : null,
  }));
  if (!price.length) throw new Error('This V2 session has no price history.');
  const rawOI = series(inputs.futures_oi);
  // Minute snapshots do not contain original receipt deltas. Do not reconstruct
  // cumulative additions/removals from them or overlapping five-minute windows.
  const oi = rawOI.length ? withCumulativeOI(rawOI, analysisStart) : price.map(row => ({
    x: row.x, t: row.t, oi: row.futures_oi ?? null, d: null,
    cumPositive: null, cumNegative: null, cumFrom: null,
  })).filter(row => finite(row.oi));
  const chartHistory = series(payload.chart_history);
  const history = [...chartHistory, ...contexts].sort((a, b) => a.x - b.x);
  const rawCash = series(inputs.cash_vix);
  const cash = rawCash.length ? rawCash : history.filter(row => finite(row.vix_raw) || finite(row.cash_raw)).map(row => ({
    // Reconstructed source-minute rows may have arrived later. Keep that clock.
    x: later(row.x, row.cash_first_observed_at, row.cash_publication),
    t: row.t, minute_ist: row.cash_source_minute,
    vix_close: row.vix_raw ?? null, cash_weighted_pct: row.cash_raw ?? null,
    cash_rolling_pct: null, history_origin: row.history_origin,
  })).sort((a, b) => a.x - b.x);
  const options = withCumulativeOI(series(inputs.option_strike_oi), analysisStart);
  const rawControls = series(inputs.intraday_inventory);
  const selection = inputs.option_strike_oi?.strike_selection || inputs.strike_selection || {};
  const nativeControls = publishedControls(contexts, profile);
  const controls = (rawControls.length
    ? [...rawControls, ...nativeControls.filter(row => row.family.startsWith('V2_'))]
    : nativeControls).sort((a, b) => a.x - b.x);
  return {
    profile, session: payload.session, price, oi, cash, calls, options, controls,
    prior: inputs.inventory_context?.controls || [], selection, transitions: [], zones: [], states: [],
    config: {}, contexts, contextHistory: history, analysisStart,
    optionClimaxes: optionClimaxPoints(contexts, price, payload.session, selection),
    start: price[0].x, end: Math.max(price.at(-1).x, contexts.at(-1)?.x || 0, calls.at(-1)?.x || 0),
    capabilities: { strikeReceipts: options.length > 0, cumulativeFutures: rawOI.length > 0 },
    provenance: { ...payload.provenance,
      call_source: profile.callLabel,
      price_note: rawPrice.length ? 'High and low use the available price receipts.' : 'High and low use retained minute closes; tick extremes are unavailable.',
      history_note: payload.provenance?.history_note || payload.chart_history_note || (payload.historical_reconstruction || contexts.some(r => r.historical_reconstruction)
        ? 'Reconstructed session. Reference calls retain the supplied replay availability times.' : ''),
      input_note: options.length ? (inputs.provenance?.note || 'Individual strike receipts retained.')
        : 'This V2 export contains basket aggregates. Individual strike receipts and session cumulative option flows are unavailable.',
      timing_note: rawControls.length ? (inputs.provenance?.timing_note || '')
        : 'VPOC values appear when retained in a V2 context. Earlier engine publication times are not inferred.',
    },
  };
}

export function normalizePayload(payload, profileId = payload.workspace_profile) {
  const profile = validatePayload(payload, profileId);
  return profile.version === '2.0.0' ? v2(payload, profile) : baseline(payload, profile);
}

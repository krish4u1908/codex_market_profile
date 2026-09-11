// Display annotation requested for V2. Uses the engine's retained ratio verbatim.
import { atOrBefore } from './series.mjs';
export const VOLUME_CLIMAX_THRESHOLD = 4;
export const VOLUME_CLIMAX_COLOR = '#ffb357';
export const FUTURES_CLIMAX_MARKER_COLOR = '#ff5f6d';

export function volumeRatioLabel(ratio) {
  if (!Number.isFinite(ratio)) return '—';
  const rounded = ratio.toFixed(2);
  // A ratio just above 4 must never be displayed as exactly 4.00.
  return `${ratio > 4 && Number(rounded) <= 4 ? String(ratio) : rounded}×`;
}

export function volumeClimaxPoints(contexts, prices, now) {
  return contexts.filter(row => row.x <= now && Number.isFinite(row.futures_volume_ratio)
    && row.futures_volume_ratio > VOLUME_CLIMAX_THRESHOLD).map(row => ({
      x: row.x, t: row.context_published_at || row.t, input_cutoff: row.input_cutoff,
      ratio: row.futures_volume_ratio, volume: row.futures_valid_volume_5m ?? null,
      price: Number.isFinite(row.index) ? row.index : atOrBefore(prices, row.x)?.i ?? null,
    }));
}

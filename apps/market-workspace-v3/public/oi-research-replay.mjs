// GUI playback only. A score boundary stops at its publication, never before it.
export function researchStep(rows, from, end, pauseOnChange) {
  const next = Math.min(end, from + 60000);
  if (!pauseOnChange || !rows?.length) return {now: next, paused: false};
  let previous = null;
  for (const row of rows) {
    if (row.x > next) break;
    if (row.source_x > row.x) continue;
    if (row.x > from && previous && row.x - previous.x <= 90000 && row.score !== previous.score)
      return {now: row.x, paused: true};
    previous = row;
  }
  return {now: next, paused: false};
}

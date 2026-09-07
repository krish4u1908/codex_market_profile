import { normalizePayload, validatePayload } from './payload-adapters.mjs';
import { frameAt } from './market-data.mjs';
let data = null, loadGeneration = 0, fetchController = null;

async function decode(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes[0] === 31 && bytes[1] === 139) {
    return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
  }
  return JSON.parse(new TextDecoder().decode(bytes));
}

self.onmessage = async event => {
  const { id, action, url, file, profileId, now, direction } = event.data;
  try {
    if (action === 'load' || action === 'file') {
      const generation = ++loadGeneration;
      fetchController?.abort();
      fetchController = new AbortController();
      data = null;
      let buffer;
      if (action === 'file') buffer = await file.arrayBuffer();
      else {
        const response = await fetch(url, { cache: 'no-store', signal: fetchController.signal });
        if (!response.ok) throw new Error(`Session could not be loaded (${response.status}).`);
        buffer = await response.arrayBuffer();
      }
      const payload = await decode(buffer);
      if (action === 'file') {
        validatePayload(payload, profileId, { allowUnidentified: true });
        // The user explicitly chose this workspace when opening the local file.
        payload.workspace_profile = profileId;
      }
      const candidate = normalizePayload(payload, profileId);
      if (generation !== loadGeneration) return;
      data = candidate;
      self.postMessage({ id, kind: 'loaded', meta: {
        session: data.session, start: data.start, end: data.end,
        analysisStart: data.analysisStart, provenance: data.provenance,
      } });
    } else if (action === 'frame') {
      if (!data) throw new Error('Select a session first.');
      self.postMessage({ id, kind: 'frame', frame: frameAt(data, now) });
    } else if (action === 'seek-event') {
      if (!data) throw new Error('Select a session first.');
      const events = [...data.transitions, ...data.controls].sort((a, b) => a.x - b.x)
        .filter(r => direction > 0 ? r.x > now : r.x < now);
      const target = direction > 0 ? events[0] : events.at(-1);
      self.postMessage({ id, kind: 'seek', now: target?.x ?? now });
    }
  } catch (error) {
    if (error.name !== 'AbortError') self.postMessage({ id, kind: 'error', error: error.message || String(error) });
  }
};

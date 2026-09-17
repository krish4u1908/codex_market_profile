import {pressureReportVix} from './pressure-direction.mjs';
import {fixedPressure} from './oi-fixed-pressure.mjs';
import { normalizePayload, validatePayload } from './payload-adapters.mjs';
import { frameAt } from './market-data.mjs';
import { oiEntryBubbles } from './oi-entry-bubbles.mjs';
import { optionOiMinuteFlows } from './option-oi-flow.mjs';
let data = null, loadGeneration = 0, fetchController = null, liveTimer = null, liveEtag = null;
let lastFrameRequest = null;

function cancelLoad() {
  loadGeneration++;
  clearTimeout(liveTimer);
  liveTimer = null;
  fetchController?.abort();
  fetchController = new AbortController();
  liveEtag = null;
  lastFrameRequest = null;
  return loadGeneration;
}

// Historical native replay stays usable while its quote archive loads. This
// path is used only for this server's catalog, never for a local file import.
async function enrichReplay(profileId, session, generation, candidate) {
  let feed;
  const signal = fetchController.signal;
  try {
    for(let attempt=0;attempt<30;attempt++) {
      if(generation!==loadGeneration)return;
      const response=await fetch(`/api/option-report-inputs?profile=${encodeURIComponent(profileId)}&session=${encodeURIComponent(session)}`,{cache:'no-store',signal});
      if(!response.ok)throw new Error('Raw option-report quotes unavailable. Core 3.0.2 is required.');
      feed=await response.json();
      if(response.status!==202)break;
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  } catch(error) {
    if(error.name==='AbortError')return;
    feed={schema:'OPTION_REPORT_INPUTS_V1',instrument:candidate.profile.instrument,session,status:'UNAVAILABLE',error:error.message};
  }
  if(generation!==loadGeneration||data!==candidate)return;
  if(feed?.status==='PENDING')feed={...feed,status:'UNAVAILABLE',error:'Option-report archive is still loading. Reopen this session to retry.'};
  data.entryAnalysis=oiEntryBubbles(data,feed);
  data.optionOiFlowAnalysis=optionOiMinuteFlows(data,feed);
  data.fixedOiPressure=fixedPressure(data,feed);
  data.oiDirectionVix=pressureReportVix(data,feed);
  data.end=Math.max(data.end,data.entryAnalysis.lastReportAt||0,data.optionOiFlowAnalysis.lastReportAt||0);
  if(lastFrameRequest)self.postMessage({id:lastFrameRequest.id,kind:'frame',frame:frameAt(data,lastFrameRequest.now),
    meta:{session:data.session,start:data.start,end:data.end,analysisStart:data.analysisStart,provenance:data.provenance}});
}

async function pollLive(id, profileId, interval, generation) {
  if (generation !== loadGeneration) return;
  try {
    const signal = fetchController.signal;
    // Health is independent from full snapshot parsing and includes feed age.
    const healthResponse = await fetch('/api/health', { cache:'no-store', signal });
    if (!healthResponse.ok) throw new Error('The shared core is unavailable. Retrying…');
    const health = await healthResponse.json();
    if (generation !== loadGeneration) return;
    if (data && health.session && health.session !== data.session) {
      data = null;
      liveEtag = null;
      self.postMessage({id, kind:'live-reset', health});
    }
    self.postMessage({id, kind:'live-status', health});
    const response = await fetch(`/api/live?profile=${encodeURIComponent(profileId)}`, {
      cache:'no-store', signal, headers: liveEtag ? {'If-None-Match':liveEtag} : {},
    });
    if (response.status === 503) return;
    if (response.status === 304) {
      self.postMessage({id, kind:'live-connected', health});
      return;
    }
    if (!response.ok) throw new Error(`Live data is unavailable (${response.status}). Retrying…`);
    const payload = await decode(await response.arrayBuffer());
    const candidate = normalizePayload(payload, profileId);
    if (generation !== loadGeneration) return;
    const serverTime=Date.parse(payload.live?.server_time);
    const close=Date.parse(`${candidate.session}T15:30:00+05:30`);
    candidate.end=Math.max(candidate.end,candidate.cash.at(-1)?.x||0,
      Number.isFinite(serverTime)&&serverTime<=close?serverTime:0);
    data = candidate;
    liveEtag = response.headers.get('ETag');
    self.postMessage({id, kind:'live-frame', health,
      meta:{session:data.session,start:data.start,end:data.end,analysisStart:data.analysisStart,provenance:data.provenance},
      frame:frameAt(data, data.end, {live:true})});
  } catch (error) {
    if (generation === loadGeneration && error.name !== 'AbortError') {
      self.postMessage({id, kind:'live-error', error:error.message || String(error)});
    }
  } finally {
    if (generation === loadGeneration) liveTimer = setTimeout(() => pollLive(id, profileId, interval, generation), interval);
  }
}

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
    if (action === 'stop') {
      cancelLoad();
      data = null;
    } else if (action === 'live') {
      const generation = cancelLoad();
      data = null;
      const interval = Math.max(1000, Number(event.data.interval) || 5000);
      void pollLive(id, profileId, interval, generation);
    } else if (action === 'load' || action === 'file') {
      const generation = cancelLoad();
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
      if(action==='load'&&String(url).startsWith('/api/replay?')&&profileId.endsWith('-v200')&&payload.option_report_inputs?.status!=='AVAILABLE') {
        data.entryAnalysis={...data.entryAnalysis,status:'PENDING',reason:'Loading option-report quotes…'};
        data.optionOiFlowAnalysis={...data.optionOiFlowAnalysis,status:'PENDING',reason:'Loading option-report quotes…'};
        data.fixedOiPressure={...data.fixedOiPressure,status:'PENDING',reason:'Loading archived option-report quotes…'};
        void enrichReplay(profileId,data.session,generation,data);
      }
    } else if (action === 'frame') {
      if (!data) throw new Error('Select a session first.');
      lastFrameRequest={id,now};
      self.postMessage({ id, kind: 'frame', frame: frameAt(data, now) });
    } else if (action === 'seek-event') {
      if (!data) throw new Error('Select a session first.');
      const events = [...data.transitions, ...data.controls, ...(data.entryAnalysis?.events||[])].sort((a, b) => a.x - b.x)
        .filter(r => direction > 0 ? r.x > now : r.x < now);
      const target = direction > 0 ? events[0] : events.at(-1);
      self.postMessage({ id, kind: 'seek', now: target?.x ?? now });
    }
  } catch (error) {
    if (error.name !== 'AbortError') self.postMessage({ id, kind: 'error', error: error.message || String(error) });
  }
};

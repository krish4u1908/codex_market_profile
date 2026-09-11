#!/usr/bin/env node
import { readFile, mkdir, writeFile, rename } from 'node:fs/promises';
import { gzipSync, gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizePayload, validatePayload } from '../public/payload-adapters.mjs';
import { getProfile } from '../public/profiles.mjs';

export async function readSession(path) {
  const bytes = await readFile(path);
  return { payload: JSON.parse((bytes[0] === 31 && bytes[1] === 139 ? gunzipSync(bytes) : bytes).toString('utf8')),
    sha256: createHash('sha256').update(bytes).digest('hex') };
}

export async function importSession({profileId, file, chartInputs, note, output = 'public/data'}) {
  const profile = getProfile(profileId);
  const source = await readSession(file);
  const payload = source.payload;
  validatePayload(payload, profileId, { allowUnidentified: true });
  if (chartInputs) {
    if (profile.version !== '2.0.0') throw new Error('--chart-inputs is only for V2 sessions.');
    const input = await readSession(chartInputs);
    const inputProfile = profile.instrument === 'NIFTY' ? 'nifty-v1062' : 'banknifty-v1062';
    validatePayload(input.payload, inputProfile, { allowUnidentified: true });
    if (input.payload.session !== payload.session) throw new Error('Chart inputs must match the V2 session date.');
    const future = payload.futures_symbol || payload.source_provenance?.futures_symbol;
    if (future && input.payload.summary?.futures_symbol && future !== input.payload.summary.futures_symbol) {
      throw new Error('Chart inputs use a different futures contract.');
    }
    if (payload.source_integrity && input.payload.summary?.artifact_sha256) {
      for (const key of ['basis','futures_market','option_strike_oi']) {
        const native = payload.source_integrity[key], companion = input.payload.summary.artifact_sha256[key];
        if (native && companion && native !== companion) throw new Error(`Chart input fingerprint mismatch: ${key}`);
      }
    }
    // Shared market receipts only. No v1 calls, inventory controls or prior levels
    // are transplanted into V2. Native V2 decisions continue to supply those levels.
    const fields = ['price', 'futures_oi', 'cash_vix', 'option_strike_oi'];
    payload.chart_inputs = Object.fromEntries(fields.map(key => [key, input.payload[key]]));
    Object.assign(payload.chart_inputs, { session: payload.session, instrument: profile.instrument,
      provenance: { source_sha256: input.sha256,
        note: 'Shared historical market receipts. Reference calls and controls come from the native V2 session.' } });
  }
  payload.workspace_profile = profileId;
  payload.provenance = {...payload.provenance, source_sha256: source.sha256,
    source_binding: 'EXPLICIT_IMPORT_PROFILE', instrument: profile.instrument, engine_version: profile.version,...(note?{history_note:note}:{})};
  const normalized = normalizePayload(payload, profileId);
  const root = resolve(output, profileId);
  await mkdir(root, {recursive:true});
  const name = `${payload.session}.json.gz`;
  let catalog = {profile:profileId, sessions:[]};
  try { catalog = JSON.parse(await readFile(join(root,'catalog.json'),'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if ((catalog.profile && catalog.profile !== profileId) || !Array.isArray(catalog.sessions)) throw new Error('Catalog profile or structure mismatch.');
  // Reject malformed data before replacing either the payload or catalog.
  const bytes = gzipSync(JSON.stringify(payload), {level:6});
  await writeFile(join(root, `${name}.tmp`), bytes);
  await rename(join(root, `${name}.tmp`), join(root, name));
  const entry = {session:payload.session, payload:`/data/${profileId}/${name}`,
    source_sha256:source.sha256, calls:normalized.calls.length, individual_strikes:normalized.capabilities.strikeReceipts};
  catalog = {profile:profileId, sessions:[...catalog.sessions.filter(row => row.session !== payload.session),entry]
    .sort((a,b) => b.session.localeCompare(a.session))};
  await writeFile(join(root,'catalog.json.tmp'),JSON.stringify(catalog,null,2)+'\n');
  await rename(join(root,'catalog.json.tmp'),join(root,'catalog.json'));
  return {profile:profileId, session:payload.session, calls:normalized.calls.length, file:join(root,name)};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), options = {};
  for (let i=0;i<args.length;i+=2) {
    if (!['--profile','--file','--chart-inputs','--output','--note'].includes(args[i]) || !args[i+1]) {
      throw new Error('Usage: node scripts/import-session.mjs --profile <workspace> --file <session.json[.gz]> [--chart-inputs <prepared-inputs.json>] [--output public/data]');
    }
    options[args[i]] = args[i+1];
  }
  if (!options['--profile'] || !options['--file']) throw new Error('--profile and --file are required.');
  console.log(JSON.stringify(await importSession({profileId:options['--profile'],file:options['--file'],chartInputs:options['--chart-inputs'],note:options['--note'],output:options['--output']})));
}

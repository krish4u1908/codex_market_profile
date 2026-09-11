import { PROFILES } from './profiles.mjs';

export const STATIC_CONFIG = Object.freeze({live:false,profiles:Object.keys(PROFILES),defaultProfile:'banknifty-v1062',defaultMode:'replay',pollMilliseconds:5000});

export function validateWorkspaceConfig(raw) {
  if (!raw || !Array.isArray(raw.profiles) || !raw.profiles.length || raw.profiles.some(id=>!Object.hasOwn(PROFILES,id))) throw new Error('Invalid workspace configuration.');
  if (!raw.profiles.includes(raw.defaultProfile)) throw new Error('Invalid default workspace.');
  if (raw.instrument && raw.profiles.some(id=>PROFILES[id].instrument!==raw.instrument)) throw new Error('Workspace configuration mixes instruments.');
  return {...raw,live:raw.live===true,defaultMode:raw.live===true&&raw.defaultMode==='live'?'live':'replay',pollMilliseconds:Math.max(1000,Number(raw.pollMilliseconds)||5000)};
}

export async function loadWorkspaceConfig() {
  const response = await fetch('/workspace-config.json', {cache:'no-store'});
  if (response.status === 404) return STATIC_CONFIG;
  if (!response.ok) throw new Error('Workspace configuration is unavailable.');
  // Static preview servers may return their index document for an unknown URL.
  if (!(response.headers.get('content-type') || '').includes('application/json')) return STATIC_CONFIG;
  return validateWorkspaceConfig(await response.json());
}

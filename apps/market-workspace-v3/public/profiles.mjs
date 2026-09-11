// GUI identities only. Both versions consume one shared core per instrument.
export const PROFILES = Object.freeze(Object.fromEntries([
  ['banknifty-v1062', 'BANKNIFTY', 'Bank Nifty', 'BN', '1.0.62', 100],
  ['nifty-v1062', 'NIFTY', 'Nifty 50', 'NIFTY', '1.0.62', 50],
  ['banknifty-v200', 'BANKNIFTY', 'Bank Nifty', 'BN', '2.0.0', 100],
  ['nifty-v200', 'NIFTY', 'Nifty 50', 'NIFTY', '2.0.0', 50],
].map(([id, instrument, label, shortLabel, version, strikeStep]) => [id, Object.freeze({
  id:String(id), instrument:String(instrument), label:String(label), shortLabel:String(shortLabel), version:String(version), strikeStep:Number(strikeStep),
  title: `${instrument} · v${version}`,
  callLabel: version === '2.0.0' ? 'V2 reference call · v1.0.62 rules' : 'v1.0.62 corrected call',
  catalog: `/data/${id}/catalog.json`,
})])));

export function getProfile(id) {
  if (!Object.hasOwn(PROFILES, id)) throw new Error(`Unknown workspace: ${id}`);
  return PROFILES[id];
}

export function instrumentOf(value) {
  if (typeof value !== 'string') return null;
  const text = value.toUpperCase();
  if (text === 'BANKNIFTY' || text === 'NIFTYBANK' || text === 'NSE:NIFTYBANK-INDEX' || /^NSE:BANKNIFTY\d/.test(text)) return 'BANKNIFTY';
  if (['NIFTY', 'NIFTY50', 'NIFTY 50', 'NSE:NIFTY50-INDEX'].includes(text) || /^NSE:NIFTY\d/.test(text)) return 'NIFTY';
  return null;
}

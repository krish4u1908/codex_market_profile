export type Row = Record<string, any>;
export type Frame = {
  profile:Row; capabilities:{strikeReceipts:boolean;cumulativeFutures:boolean}; context:Row|null; contextHistory:Row[]; volumeHistory:Row[]; volumeClimaxes:Row[];
  session:string; now:number; start:number; end:number; analysisStart:number;
  price:Row[]; latest:Row|null; oi:Row[]; cash:Row[]; call:Row|null; state:Row|null;
  selection:Row; controls:Row[]; controlHistory:Row[]; prior:Row[];
  options:Row[]; snapshots:Row[]; transitions:Row[]; zones:Row[];
  optionProfile:{rows:Row[];scale:number;support:number|null;resistance:number|null;oldestReceipt:number|null;newestReceipt:number|null;partial:boolean;expiry:string|null};
  range:{high:number|null;low:number|null;open:number|null}; provenance:Row;
  vixRange:{high:number|null;low:number|null;from:number|null};
  basisRange:{high:number|null;low:number|null};
};
export const COLORS={price:'#54cfff',basis:'#bb9cff',oi:'#f6cc6b',vix:'#f3a77c',cash:'#69d3bb',positive:'#46d8a4',negative:'#ff768c',muted:'#92a4bd'};
export const STRIKES=['#52cfff','#ebc465','#b099f6','#54d5ab'];
export const LEVELS:Record<string,{label:string;color:string}>={
  FUT_POS_OI_VPOC:{label:'Futures +OI',color:'#69dba7'},FUT_NEG_OI_VPOC:{label:'Futures −OI',color:'#fc8696'},
  CE_POS_OI_VPOC:{label:'CE +OI',color:'#f4b069'},CE_NEG_OI_VPOC:{label:'CE −OI',color:'#ed8dc4'},
  PE_POS_OI_VPOC:{label:'PE +OI',color:'#64d2c3'},PE_NEG_OI_VPOC:{label:'PE −OI',color:'#a1b7ff'},
  V2_RECENT_VOLUME_VPOC:{label:'Volume · recent 15m',color:'#ed8dc4'},
  V2_RECONSTRUCTED_VOLUME_VPOC:{label:'Volume · reconstructed cumulative',color:'#f6cc6b'},
  NIFTY_REF_FUT_VOLUME_VPOC:{label:'Futures volume',color:'#54cfff'},
  BN_REF_FUT_VOLUME_VPOC:{label:'Futures volume',color:'#54cfff'},
};
export const fmt=(value:any,digits=2)=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString('en-IN',{minimumFractionDigits:digits,maximumFractionDigits:digits});
export const compact=(v:any)=>v==null?'—':Math.abs(v)>=1e7?`${fmt(v/1e7,2)}Cr`:Math.abs(v)>=1e5?`${fmt(v/1e5,2)}L`:Math.abs(v)>=1e3?`${fmt(v/1e3,1)}K`:fmt(v,0);
export const signed=(value:any,digits=2)=>value==null?'—':`${value>0?'+':''}${fmt(value,digits)}`;
export const clock=(value:any,seconds=false)=>!value?'—':new Date(value).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour12:false,hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{})});
export const words=(s:any)=>String(s||'Unavailable').replaceAll('_',' ').toLowerCase();

// Small synthetic contracts for tests only. Never served as market data.
export const day='2026-09-03';
export const t = time => `${day}T${time}+05:30`;
export const ms = time => Date.parse(t(time));
export function v1(instrument='BANKNIFTY') {
  const nifty=instrument==='NIFTY', atm=nifty?24000:57400, step=nifty?50:100;
  const symbol=(strike,side)=>`NSE:${instrument}26SEP${strike}${side}`;
  const selection={available:true,selected_at:t('09:45:55'),atm,expiry:'2026-09-29',
    CE:[0,1,2,3].map(i=>({strike:atm+i*step,symbol:symbol(atm+i*step,'CE')})),
    PE:[0,1,2,3].map(i=>({strike:atm-i*step,symbol:symbol(atm-i*step,'PE')}))};
  const options=[];
  for(const [time,delta,oi] of [['09:45:55',null,100],['09:46:55',30,130],['09:47:55',-10,120]]) {
    for(const side of ['CE','PE']) for(const c of selection[side]) options.push({t:t(time),e:selection.expiry,
      k:side,s:c.strike,symbol:c.symbol,oi,d:delta,p:100,v:400,dv:delta==null?null:50});
  }
  const cash=nifty?[]:[{t:t('09:46:08'),minute_ist:t('09:45:00'),vix_close:11.1},{t:t('09:48:08'),minute_ist:t('09:47:00'),vix_close:10.9}];
  return {schema:'NEW_DIVERGENCE_BROWSER_PAYLOAD_V1',session:day,instrument,
    price:[{t:t('09:15:59'),i:atm,b:-4,f:atm-4},{t:t('09:44:59'),i:atm+40,b:5,f:atm+45},
      {t:t('09:46:59'),i:atm+10,b:-2,f:atm+8},{t:t('10:00:00'),i:atm-10,b:7,f:atm-3}],
    futures_oi:[{t:t('09:45:55'),symbol:`NSE:${instrument}26SEPFUT`,oi:1000,d:null},
      {t:t('09:46:55'),symbol:`NSE:${instrument}26SEPFUT`,oi:1100,d:100},
      {t:t('09:47:55'),symbol:`NSE:${instrument}26SEPFUT`,oi:1060,d:-40}],
    cash_vix:cash,option_strike_oi:{fields:Object.keys(options[0]),rows:options.map(Object.values),strike_selection:selection},
    intraday_inventory:[{t:t('09:46:55'),family:'PE_NEG_OI_VPOC',scope:'ID',status:'AVAILABLE',control_value:atm},
      {t:t('09:55:55'),family:'PE_NEG_OI_VPOC',scope:'ID',status:'AVAILABLE',control_value:atm-25}],
    directional_prediction:[{t:t('09:46:08'),published_at:t('09:46:08'),input_cutoff:t('09:46:00'),
      decision_id:'fixture-call-1',direction:'UP',score:3.5,state:'UP_PRESSURE',confidence:'LOW',horizon_minutes:5,
      drivers:['Recorded driver'],invalidation:'Retained statement',strategy:'corrected',quality:{status:nifty?'DEGRADED':'COMPLETE',issues:nifty?{vix:'MISSING'}:{}}}],
    transitions:[],states:[],confirmed_zones:[]};
}
export function v2(instrument='BANKNIFTY',{receipts=false}={}) {
  const input=v1(instrument), atm=input.option_strike_oi.strike_selection.atm;
  const c={session:day,t:t('09:48:09'),context_published_at:t('09:48:09'),input_cutoff:t('09:48:00'),
    corrected_direction:'UP',corrected_score:3.5,baseline_call:input.directional_prediction[0],complete:false,missing_inputs:['vix_raw_change_5m'],
    ce_oi:400,pe_oi:600,ce_oi_delta_5m:20,pe_oi_delta_5m:-10,ce_oi_additions_5m:30,ce_oi_reductions_5m:10,
    pe_oi_additions_5m:10,pe_oi_reductions_5m:20,ce_coverage:4,pe_coverage:4,fixed_atm:atm,
    fut_pos_oi_vpoc:atm, fut_neg_oi_vpoc:atm-25,ce_pos_oi_vpoc:atm,ce_neg_oi_vpoc:atm+25,
    pe_pos_oi_vpoc:atm-25,pe_neg_oi_vpoc:atm,volume_cumulative_mode_canonical:atm};
  return {version:'2.0.0',baseline_version:'1.0.62',instrument,session:day,decisions:[c],
    price_history:input.price.map(r=>({t:r.t,index:r.i,basis:r.b,futures_oi:1000})),
    chart_history:[{t:t('09:46:00'),history_origin:'RECONSTRUCTED_INPUT_HISTORY',ce_oi_delta_5m:12,
      cash_first_observed_at:t('09:49:00'),cash_source_minute:t('09:45:00'),vix_raw:instrument==='NIFTY'?null:11.2}],
    ...(receipts?{chart_inputs:{session:day,instrument,price:input.price,futures_oi:input.futures_oi,
      option_strike_oi:input.option_strike_oi,cash_vix:input.cash_vix}}:{})};
}

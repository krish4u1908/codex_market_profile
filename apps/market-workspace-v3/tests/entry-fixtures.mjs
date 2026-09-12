// Synthetic only: these fixtures are never included in deployment assets.
export function entryFixture(instrument='NIFTY',side='PE',{vixSign=side==='PE'?1:-1}={}) {
  const session='2026-09-11',ms=s=>Date.parse(`${session}T${s}+05:30`),iso=x=>new Date(x).toISOString();
  const step=instrument==='NIFTY'?50:100,atm=instrument==='NIFTY'?23300:57400,spot=atm+step/2;
  const expiry='2026-09-29',start=ms('09:15:00'),event=ms('10:00:55'),direction=side==='PE'?1:-1;
  const options=[],price=[];
  for(let x=ms('09:35:00');x<=ms('10:05:00');x+=1000)price.push({t:iso(x),i:spot,f:spot+40,b:40,age:196});
  for(let slot=0;slot<3;slot++) {
    const strike=side==='PE'?atm-slot*step:atm+(slot+1)*step,symbol=`NSE:${instrument}26SEP${strike}${side}`;
    let previous=null;
    for(let i=0;i<=25;i++) {
      const oi=i===25?previous*.98:100000+i*100,x=ms('09:35:55')+i*60000;
      options.push({t:iso(x),s:strike,k:side,symbol,e:expiry,oi,d:previous===null?null:oi-previous,
        p:100+i*.1,v:i*1000,dv:1000,event_id:`report-${i}`});previous=oi;
    }
  }
  const cash=Array.from({length:6},(_,i)=>({t:iso(ms('09:55:08')+i*60000),
    minute_ist:iso(ms('09:54:00')+i*60000),vix_close:i===5?100+vixSign*.5:100,
    cash_weighted_pct:direction*.2,cash_names:10,expected_constituent_count:10,available_weight:100}));
  const context={t:iso(ms('10:00:20')),context_published_at:iso(ms('10:00:20')),input_cutoff:iso(ms('10:00:00')),
    session,broader_leg:direction,volume_cumulative_mode_canonical:spot-direction*step,
    corrected_direction:direction===1?'UP':'DOWN',cash_raw:direction*.2};
  const selection={available:true,selected_at:iso(ms('09:45:00')),expiry,CE:[],PE:[]};
  return {event,ms,iso,options,spot,step,payload:{version:'2.0.0',baseline_version:'1.0.62',instrument,session,
    decisions:[context],chart_inputs:{session,instrument,price,cash_vix:cash,
      option_strike_oi:{fields:Object.keys(options[0]),rows:options.map(Object.values),strike_selection:selection}}}};
}

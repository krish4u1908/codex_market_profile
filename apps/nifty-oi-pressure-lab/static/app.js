const $=id=>document.getElementById(id);
let rows=[], idx=0, regime='expiry', timer=null, summary={};
const fmt=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
const signed=(v,d=2)=>v==null?'—':`${v>0?'+':''}${Number(v).toFixed(d)}`;
const hm=t=>{try{return t.substring(11,16)}catch{return t}};
function score(r){return Number(regime==='expiry'?(r.expiry_bear_score||0):(r.normal_oi_score||0));}
function layersFor(r){
 if(regime==='expiry') return [
  ['Micro fixed 4 · 1m',!!r.MICRO_FIXED4_1M,'Fast transition'],['Dynamic near-ATM 4 · 5m',!!r.NEAR_DYN4_5M,'Current strikes'],['Whole chain · 10m',!!r.BROAD_FULL_10M,'Broad regime']
 ];
 return [
  ['Bull fixed4 fast',!!r.BULL_FIXED4_FAST,'Bull'],['Bull dynamic near',!!r.BULL_DYN4_NEAR,'Bull'],['Bull broad chain',!!r.BULL_FULL_BROAD,'Bull'],
  ['Bear fixed2 fast',!!r.BEAR_FIXED2_FAST,'Bear'],['Bear dynamic regime',!!r.BEAR_DYN4_REGIME,'Bear'],['Bear activity',!!r.BEAR_FULL_ACTIVITY,'Bear']
 ];
}
function stateFor(s){let a=Math.abs(s); if(a<35)return 'NEUTRAL'; if(a<70)return s<0?'WATCH BEAR':'WATCH BULL'; if(a<100)return s<0?'HIGH BEAR':'HIGH BULL'; return s<0?'VERY HIGH BEAR':'VERY HIGH BULL';}
function persistence(i){
 let s=score(rows[i]); if(Math.abs(s)<35){
   for(let j=Math.max(0,i-4);j<i;j++) if(Math.abs(score(rows[j]))>=70) return 'RESETTING';
   return 'NO REGIME';
 }
 let sign=Math.sign(s), n=0; for(let j=i;j>=0 && j>=i-5;j--){let x=score(rows[j]); if(Math.abs(x)>=35&&Math.sign(x)===sign)n++; else break;}
 if(n>=3)return 'LOCKED'; if(n>=2)return 'PERSISTING';
 if(i>0 && Math.sign(score(rows[i-1]))===-sign && Math.abs(score(rows[i-1]))>=35)return 'REVERSED';
 return 'DEVELOPING';
}
function disagreement(r,s){let p=Number(r.prior_ret_3m||0); if(s<=-35 && p>0)return 'BEARISH OI vs PRICE BOUNCE'; if(s>=35 && p<0)return 'BULLISH OI vs PRICE DIP'; return 'NONE';}
async function loadSessions(){regime=$('regime').value; let x=await fetch(`/api/sessions?regime=${regime}`).then(r=>r.json()); $('session').innerHTML=x.sessions.map(s=>`<option>${s}</option>`).join(''); if(regime==='expiry'&&x.sessions.includes('2026-09-15'))$('session').value='2026-09-15'; await loadTimeline();}
async function loadTimeline(){stop(); let s=$('session').value; let x=await fetch(`/api/timeline?regime=${regime}&session=${s}`).then(r=>r.json()); rows=x.rows; summary=x.summary; idx=0; $('scrubber').max=Math.max(0,rows.length-1); $('scrubber').value=0; render();}
function render(){if(!rows.length)return; let r=rows[idx], s=score(r), st=stateFor(s), per=persistence(idx), dis=disagreement(r,s); $('score').textContent=s>0?`+${s}`:s; $('score').className='score '+(s<0?'bear':s>0?'bull':'neutral'); $('state').textContent=st; $('persist').textContent=per; $('persist2').textContent=per; $('needle').style.left=`${Math.max(0,Math.min(100,(s+100)/2))}%`; $('spot').textContent=fmt(r.spot,2); $('clock').textContent=`${r.session} · ${hm(r.time)}`; $('prior').textContent=signed(r.prior_ret_3m,2); $('prior').className=Number(r.prior_ret_3m)>0?'bulltext':Number(r.prior_ret_3m)<0?'beartext':''; $('disagree').textContent=`Price/OI disagreement: ${dis}`; $('disagree2').textContent=dis; let l=layersFor(r), active=l.filter(x=>x[1]); $('votes').textContent=active.length; $('layerText').textContent=active.length?active.map(x=>x[0]).join(' · '):'No confirmations'; $('layers').innerHTML=l.map(x=>`<div class="layer ${x[1]?'on':''} ${x[2]==='Bull'?'bull':''}"><span><i class="dot"></i>${x[0]}</span><b>${x[1]?'ACTIVE':'off'}</b></div>`).join('');
 const signalTone=s<0?'bear':s>0?'bull':'neutral';
 const stateTag=`<span class="sig-tag state-tag ${signalTone}">${st}</span>`;
 const layerTags=active.map(x=>`<span class="sig-tag layer-tag ${x[2]==='Bull'?'bull':(x[2]==='Bear'?'bear':'neutral')}">${x[0]}</span>`).join('');
 $('signalTags').innerHTML=stateTag + (active.length? layerTags : `<span class="sig-tag info-tag neutral">No active layer</span>`);
 let mech='No directional OI regime is confirmed at this minute.'; if(s<0)mech=dis.startsWith('BEARISH')?'Price is bouncing while OI remains bearish — prototype failed-recovery / continuation condition.':'Bearish OI structure is active. Stronger interpretation requires persistence and/or price disagreement.'; if(s>0)mech=dis.startsWith('BULLISH')?'Price is dipping while OI remains bullish — prototype failed-breakdown / continuation condition.':'Bullish OI structure is active. Bullish side remains less validated in the current sample.'; $('mechanism').textContent=mech;
 $('f10').textContent=signed(r.fut_ret_10m,2); $('f15').textContent=signed(r.fut_ret_15m,2); $('resetExplain').textContent= per==='LOCKED' ? 'The directional OI regime has persisted across multiple observations. A price move against it without score normalization is treated as rejection, not a reset.' : per==='RESETTING' ? 'A previously strong regime has moved back toward neutral. Treat continuation assumptions cautiously until direction re-establishes.' : 'Prototype reset state is derived causally from recent score persistence; it does not use future returns.';
 $('idxLabel').textContent=`${idx+1} / ${rows.length}`; $('scrubber').value=idx; renderStats(); renderTable(); draw();}
function renderStats(){let e=summary.episodes||{}, h=summary.strong||{}; $('stats').innerHTML=`<div class=stat><span>Episodes ≥35</span><strong>${e.n??0}</strong></div><div class=stat><span>10m directional hit</span><strong>${e.hit10==null?'—':e.hit10+'%'}</strong></div><div class=stat><span>Strong ≥70</span><strong>${h.n??0}</strong></div><div class=stat><span>Strong 10m hit</span><strong>${h.hit10==null?'—':h.hit10+'%'}</strong></div>`;}
function renderTable(){let a=Math.max(0,idx-5),b=Math.min(rows.length,idx+6); $('tbody').innerHTML=rows.slice(a,b).map((r,k)=>{let i=a+k,s=score(r),n=layersFor(r).filter(x=>x[1]).length;return `<tr class="${i===idx?'selrow':''}"><td>${hm(r.time)}</td><td>${fmt(r.spot)}</td><td>${signed(r.prior_ret_3m)}</td><td class="${s<0?'beartext':s>0?'bulltext':''}">${s>0?'+':''}${s}</td><td>${n}</td><td>${signed(r.fut_ret_5m)}</td><td>${signed(r.fut_ret_10m)}</td><td>${signed(r.fut_ret_15m)}</td></tr>`}).join('');}
function drawCanvas(id,key,minmax){let c=$(id),ctx=c.getContext('2d'),W=c.width,H=c.height;ctx.clearRect(0,0,W,H);ctx.fillStyle='#09131c';ctx.fillRect(0,0,W,H);let pad={l:52,r:15,t:15,b:28};let vals=rows.map(r=>key==='score'?score(r):Number(r.spot)).filter(Number.isFinite);let mn=minmax?minmax[0]:Math.min(...vals),mx=minmax?minmax[1]:Math.max(...vals); if(mx===mn)mx=mn+1; ctx.strokeStyle='#1b2b39';ctx.lineWidth=1;ctx.font='11px system-ui';ctx.fillStyle='#7590a5';for(let g=0;g<5;g++){let y=pad.t+(H-pad.t-pad.b)*g/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();let v=mx-(mx-mn)*g/4;ctx.fillText(key==='score'?Math.round(v):v.toFixed(0),5,y+4)}
 let x=i=>pad.l+(W-pad.l-pad.r)*(i/(rows.length-1||1)), y=v=>pad.t+(H-pad.t-pad.b)*(1-(v-mn)/(mx-mn)); if(key==='score'){for(let th of [-70,-35,0,35,70]){ctx.strokeStyle=th===0?'#607386':Math.abs(th)===70?'#663541':'#665832';ctx.setLineDash(th===0?[]:[5,5]);ctx.beginPath();ctx.moveTo(pad.l,y(th));ctx.lineTo(W-pad.r,y(th));ctx.stroke();ctx.setLineDash([])}}
 ctx.strokeStyle=key==='score'?'#a78bfa':'#4dd7ff';ctx.lineWidth=2;ctx.beginPath();rows.forEach((r,i)=>{let v=key==='score'?score(r):Number(r.spot); if(!Number.isFinite(v))return; if(i===0)ctx.moveTo(x(i),y(v));else ctx.lineTo(x(i),y(v));});ctx.stroke(); let cur=key==='score'?score(rows[idx]):Number(rows[idx].spot);ctx.fillStyle=key==='score'?(cur<0?'#ff6174':cur>0?'#4ee39c':'#fff'):'#fff';ctx.beginPath();ctx.arc(x(idx),y(cur),5,0,Math.PI*2);ctx.fill(); ctx.fillStyle='#7590a5';ctx.fillText(hm(rows[0].time),pad.l,H-7);ctx.fillText(hm(rows[rows.length-1].time),W-pad.r-40,H-7);}
function draw(){drawCanvas('priceChart','spot');drawCanvas('scoreChart','score',[-100,100]);}
function playbackTick(){
 if(idx>=rows.length-1){stop();return;}
 const previousScore=score(rows[idx]);
 idx++;render();
 if($('pauseOnChange').checked && score(rows[idx])!==previousScore) stop();
}
function startTimer(){
 const delay=Number($('speed').value);
 if(!Number.isFinite(delay)||delay<200){stop();return;}
 timer=setInterval(playbackTick,delay);
}
function play(){
 if(timer){stop();return;}
 if(!rows.length)return;
 if(idx>=rows.length-1){idx=0;render();}
 $('play').textContent='❚❚ Pause';startTimer();
}
function stop(){
 if(timer){clearInterval(timer);timer=null;}
 $('play').textContent='▶ Play';
}
function step(amount){
 stop();
 if(!rows.length)return;
 idx=Math.max(0,Math.min(rows.length-1,idx+amount));render();
}

$('regime').addEventListener('change',loadSessions);$('session').addEventListener('change',loadTimeline);$('scrubber').addEventListener('input',e=>{idx=Number(e.target.value);render()});$('play').addEventListener('click',play);$('speed').addEventListener('change',()=>{if(timer){clearInterval(timer);timer=null;startTimer();}});$('prev').addEventListener('click',()=>step(-1));$('next').addEventListener('click',()=>step(1));document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey||['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;if(e.key==='ArrowLeft'){e.preventDefault();step(-1);}else if(e.key==='ArrowRight'){e.preventDefault();step(1);}});$('reset').addEventListener('click',()=>{stop();idx=0;render()});window.addEventListener('resize',draw);loadSessions();
// v0.1.2: show active signal/layer tags directly in the hero signal frame

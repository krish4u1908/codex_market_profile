// Display-only revision. Native calls, scores and synchronization are unchanged.
export const PRICE_BASIS_RIBBON_POLICY=Object.freeze({
  id:'PRICE_BASIS_RIBBON_3M_V1',windowMs:180000,baselineToleranceMs:60000,maxReceiptGapMs:90000,
});
const finite=Number.isFinite;

export function priceBasisRibbon(price,session) {
  const policy=PRICE_BASIS_RIBBON_POLICY;
  const dayStart=Date.parse(`${session}T00:00:00+05:30`);
  const rows=price.filter(r=>finite(r.x)&&r.x>=dayStart&&r.x<dayStart+86400000).slice().sort((a,b)=>a.x-b.x);
  const points=[];
  let anchor=-1,runStart=0;
  for(let index=0;index<rows.length;index++) {
    const row=rows[index],cutoff=row.x-policy.windowMs;
    const point={x:row.x,cutoff,price:row.i,basis:row.b,baselineAt:null,priceChange:null,basisChange:null,
      state:'unavailable',reason:'Waiting for 3m of continuous price/basis history'};
    if(index&&row.x-rows[index-1].x>policy.maxReceiptGapMs)runStart=index;
    while(anchor+1<index&&rows[anchor+1].x<=cutoff)anchor++;
    if(!finite(row.i)||!finite(row.b)) {
      runStart=index+1;
      point.reason='Price or basis is missing';
    } else if(anchor>=runStart&&cutoff-rows[anchor].x<=policy.baselineToleranceMs) {
      const previous=rows[anchor];
      point.baselineAt=previous.x;
      point.priceChange=row.i-previous.i;
      point.basisChange=row.b-previous.b;
      point.state=point.priceChange<0&&point.basisChange>0?'green'
        :point.priceChange>0&&point.basisChange<0?'red':'neutral';
      point.reason='';
    }
    points.push(point);
  }
  return points;
}

export function latestBasisRibbon(points,now) {
  const last=points.at(-1);
  if(!last)return null;
  if(now-last.x>PRICE_BASIS_RIBBON_POLICY.maxReceiptGapMs)return {
    ...last,state:'unavailable',priceChange:null,basisChange:null,reason:'No recent price/basis receipt',
  };
  return last;
}

export function sampleBasisRibbon(points) {
  const keep=new Set();
  for(let index=0;index<points.length;index++) {
    const row=points[index],previous=points[index-1],next=points[index+1];
    const minute=Math.floor(row.x/60000);
    if(!previous||!next||previous.state!==row.state
      ||Math.floor(previous.x/60000)!==minute||Math.floor(next.x/60000)!==minute)keep.add(row);
  }
  return [...keep];
}

// Paint forward from availability, clipped to the cursor and receipt freshness.
// Frames retain every state change plus first/last receipts of each minute.
export function basisRibbonIntervals(points,min,max) {
  return points.flatMap((point,index)=>{
    const start=Math.max(min,point.x);
    const end=Math.min(max,points[index+1]?.x??max,point.x+PRICE_BASIS_RIBBON_POLICY.maxReceiptGapMs);
    return point.state==='unavailable'||end<=start?[]:[{...point,start,end}];
  });
}

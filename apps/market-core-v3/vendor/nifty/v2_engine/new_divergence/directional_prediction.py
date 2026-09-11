"""Shared, completed-minute direction decisions. Sequence model is opt-in."""
from __future__ import annotations
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import timedelta
import hashlib
import json
from zoneinfo import ZoneInfo
from .clock import parse_instant, iso_utc
from .legacy_directional_prediction import _rows, _finite, _value, _sign, _bounded, _vpoc_modifier
from .legacy_directional_prediction import predict_direction as legacy_predict_direction

IST = ZoneInfo('Asia/Kolkata')
HORIZON_MINUTES = 5
DEFAULT_STRATEGY = 'corrected'
SERIES_FIELDS = ('t','direction','state','confidence','score','vpoc_modifier','headline','drivers',
                 'invalidation','metrics','published_at','input_cutoff','last_price_receipt','quality',
                 'context','components','strategy','decision_id','previous_direction','change_reason')


def _aligned_move(rows, cutoff, keys, max_age, max_gap):
    rows = [r for r in rows if r['_instant'] < cutoff and _value(r,*keys) is not None]
    start = cutoff-timedelta(minutes=5)
    anchors = [r for r in rows if r['_instant'] <= start]
    if not rows or not anchors: return None,'MISSING_5M_ANCHOR'
    first,last = anchors[-1],rows[-1]
    if (start-first['_instant']).total_seconds()>max_age: return None,'STALE_5M_ANCHOR'
    if (cutoff-last['_instant']).total_seconds()>max_age: return None,'STALE_LATEST'
    window = [r for r in rows if r['_instant']>=first['_instant']]
    if any((b['_instant']-a['_instant']).total_seconds()>max_gap for a,b in zip(window,window[1:])):
        return None,'GAP_IN_5M_WINDOW'
    return _value(last,*keys)-_value(first,*keys),None


def _cash_features(rows, decision_at, cutoff):
    rows = [r for r in rows if r['_instant']<=decision_at and
            (not r.get('minute_ist') or parse_instant(r['minute_ist'])<cutoff)]
    quality = {'cash':'MISSING','vix':'MISSING','age_seconds':None}
    if not rows: return None,None,quality
    latest=rows[-1]; age=(decision_at-latest['_instant']).total_seconds()
    quality['age_seconds']=round(age,3)
    if age>120:
        quality.update(cash='STALE',vix='STALE'); return None,None,quality
    # A change between two rolling 5m means requires six consecutive source minutes.
    window=rows[-6:]
    contiguous=(len(window)==6 and all(r.get('minute_ist') for r in window) and
                all(parse_instant(b['minute_ist'])-parse_instant(a['minute_ist'])==timedelta(minutes=1)
                    for a,b in zip(window,window[1:])))
    cash_valid=contiguous and all(r.get('cash_weighted_pct') is not None and
        int(r.get('expected_constituent_count') or 0)>0 and r.get('cash_names')==r.get('expected_constituent_count') and
        r.get('status') in ('VALID','INCOMPLETE_VIX') for r in window)
    vix_valid=contiguous and all((_finite(r.get('vix_close')) or 0)>0 and
        r.get('status') in ('VALID','INCOMPLETE_CASH') for r in window)
    cash=_finite(latest.get('cash_rolling_change')) if cash_valid else None
    vix=_finite(latest.get('vix_rolling_change')) if vix_valid else None
    quality['cash']='VALID' if cash is not None else 'INCOMPLETE_ROLLING_WINDOW'
    quality['vix']='VALID' if vix is not None else 'INCOMPLETE_ROLLING_WINDOW'
    return cash,vix,quality


def prepare_features(bundle):
    market=_rows(bundle.get('recent_market',[]))
    if not market: raise ValueError('direction requires synchronized price history')
    cutoff=parse_instant(bundle.get('input_cutoff') or iso_utc(market[-1]['_instant']+timedelta(microseconds=1)))
    published=parse_instant(bundle.get('decision_at') or iso_utc(cutoff))
    if published<cutoff: raise ValueError('publication precedes input cutoff')
    market=[r for r in market if r['_instant']<cutoff]
    if not market: raise ValueError('no price available before input cutoff')
    oi=_rows(bundle.get('recent_futures_oi',[])); cash_rows=_rows(bundle.get('recent_cash_vix',[]))
    metrics={'index':_value(market[-1],'i','index_price')}; issues={}
    for field,keys in [('index_change_5m',('i','index_price')),('futures_change_5m',('f','futures_price')),('basis_change_5m',('b','basis'))]:
        metrics[field],error=_aligned_move(market,cutoff,keys,15,60)
        if error: issues[field]=error
    metrics['futures_oi_change_5m'],error=_aligned_move(oi,cutoff,('oi',),90,90)
    if error: issues['futures_oi_change_5m']=error
    cash,vix,cash_quality=_cash_features(cash_rows,published,cutoff)
    metrics.update(cash_rolling_change=cash,vix_rolling_change=vix)
    for field in ('cash','vix'):
        if cash_quality[field]!='VALID': issues[field]=cash_quality[field]
    quality={'status':'COMPLETE' if not issues else 'DEGRADED','issues':issues,'cash_vix':cash_quality,
             'price_age_seconds':round((cutoff-market[-1]['_instant']).total_seconds(),3)}
    return market,metrics,quality,cutoff,published


def _minute_path(market,cutoff):
    selected=[r for r in market if r['_instant']>=cutoff-timedelta(minutes=60)]
    for n in range(len(selected)-1,0,-1):
        if (selected[n]['_instant']-selected[n-1]['_instant']).total_seconds()>60:
            selected=selected[n:]; break
    groups={}
    for r in selected:
        key=r['_instant'].replace(second=0,microsecond=0); price=_value(r,'i','index_price')
        if price is None: continue
        if key not in groups: groups[key]={'t':iso_utc(key),'open':price,'high':price,'low':price}
        groups[key].update(close=price,basis=_value(r,'b','basis'))
        groups[key]['high']=max(groups[key]['high'],price); groups[key]['low']=min(groups[key]['low'],price)
    return list(groups.values())


def sequence_context(market,cutoff,metrics):
    bars=_minute_path(market,cutoff)
    context={'session_context':'INSUFFICIENT_HISTORY','episode':'NO_ORDERED_PATTERN','events':[],
             'votes':{},'modifier':0.0,'history_minutes':len(bars),'invalidation_level':None}
    if len(bars)<6: return context
    last=bars[-1]['close']; recent=bars[-6:]
    peak=max(range(len(recent)),key=lambda n:recent[n]['high'])
    trough=min(range(len(recent)),key=lambda n:recent[n]['low'])
    gain=recent[peak]['high']-recent[0]['open']; decline=recent[0]['open']-recent[trough]['low']
    rejection=recent[peak]['high']-last; recovery=last-recent[trough]['low']
    move=metrics['index_change_5m'] or 0.0
    if 0<peak<len(recent)-1 and gain>=10 and rejection>=10 and rejection>=gain*.5:
        context['votes']['path']=-min(3.0,3.0*rejection/max(gain,10.0))
        context['episode']='RALLY_REJECTED'; context['invalidation_level']=recent[peak]['high']
        context['events'].append({'t':recent[peak]['t'],'event':'RALLY_THEN_GIVEBACK','gain':round(gain,2),'giveback':round(rejection,2)})
    elif 0<trough<len(recent)-1 and decline>=10 and recovery>=10 and recovery>=decline*.5:
        context['votes']['path']=min(3.0,3.0*recovery/max(decline,10.0))
        context['episode']='SELLOFF_RECLAIMED'; context['invalidation_level']=recent[trough]['low']
        context['events'].append({'t':recent[trough]['t'],'event':'SELLOFF_THEN_RECOVERY','decline':round(decline,2),'recovery':round(recovery,2)})
    if len(bars)>=30:
        older,newer=bars[-30:-15],bars[-15:]
        higher=max(r['high'] for r in newer)>max(r['high'] for r in older)+10 and min(r['low'] for r in newer)>min(r['low'] for r in older)+10
        lower=max(r['high'] for r in newer)<max(r['high'] for r in older)-10 and min(r['low'] for r in newer)<min(r['low'] for r in older)-10
        context['session_context']='RISING_STRUCTURE' if higher else 'FALLING_STRUCTURE' if lower else 'RANGE_OR_TRANSITION'
        context['votes']['structure']=2.0 if higher else -2.0 if lower else 0.0
    # Break, later test, then current response: never backdate a confirmed pivot.
    for n in range(max(10,len(bars)-10),len(bars)-1):
        before=bars[n-10:n]; upper=max(r['high'] for r in before); lower=min(r['low'] for r in before)
        direction=1 if bars[n]['close']>upper+10 else -1 if bars[n]['close']<lower-10 else 0
        if not direction: continue
        level=upper if direction>0 else lower; after=bars[n+1:]
        tested=any(r['low']<=level+10 if direction>0 else r['high']>=level-10 for r in after)
        if not tested: continue
        held=all(r['close']>=level-10 if direction>0 else r['close']<=level+10 for r in after)
        regained=last>level+10 if direction>0 else last<level-10
        failed=last<level-10 if direction>0 else last>level+10
        if (held and regained) or failed:
            context['votes']['retest']=direction*2.0 if held and regained else -direction*2.0
            context['episode']='BREAK_RETEST_HOLD' if held and regained else 'BREAK_FAILED'
            context['invalidation_level']=level-10*direction if held and regained else bars[n]['high' if direction>0 else 'low']
            context['events'].append({'t':bars[n]['t'],'event':context['episode'],'level':round(level,2),'break_direction':'UP' if direction>0 else 'DOWN'})
    if len(bars)>=11 and (metrics.get('futures_oi_change_5m') or 0)>0:
        prior=bars[-6]['close']-bars[-11]['close']; basis=metrics.get('basis_change_5m')
        if abs(prior)>=10 and abs(move)<abs(prior)*.5 and basis is not None and _sign(basis)==_sign(prior):
            context['votes']['flow_efficiency']=-float(_sign(prior))
            context['events'].append({'t':bars[-1]['t'],'event':'LESS_PRICE_PROGRESS_WITH_RISING_OI'})
    context['modifier']=round(sum(context['votes'].values()),4); context['events']=context['events'][-6:]
    return context


def predict_direction(bundle,*,strategy=None):
    strategy=strategy or str(bundle.get('direction_strategy') or DEFAULT_STRATEGY)
    if strategy not in ('corrected','sequence_candidate','legacy_common_inputs'): raise ValueError('unknown direction strategy')
    market,m,quality,cutoff,published=prepare_features(bundle)
    if strategy=='legacy_common_inputs':
        result=legacy_predict_direction(dict(bundle))
        result.update(input_cutoff=iso_utc(cutoff),published_at=iso_utc(published),t=iso_utc(published),strategy=strategy,quality=quality)
        result['score']=result['core_score']; return result
    price=m['index_change_5m']; futures=m['futures_change_5m']; basis=m['basis_change_5m']; oi=m['futures_oi_change_5m']
    cash=m['cash_rolling_change']; vix=m['vix_rolling_change']
    ps,fs,bs,os,cs,vs=_sign(price,.25),_sign(futures,.25),_sign(basis,.10),_sign(oi),_sign(cash,.0005),_sign(vix,.0005)
    components={'index':_bounded(price,15,3),'futures':_bounded(futures,15,2),'basis':_bounded(basis,10,1.25),
                'cash':cs*2.25,'vix':-vs*1.5,'oi_response':ps*(2 if os>0 else 1.15 if os<0 else .35) if oi is not None else 0.0}
    if not ps and fs and oi is not None: components['oi_response']=fs*(1.25 if os>0 else .65)
    score=sum(components.values()); complete=quality['status']=='COMPLETE'
    required=all(x is not None for x in (price,futures,oi,cash,vix))
    trap=required and ps>=0 and fs>=0 and bs>0 and os>0 and cs<0 and vs>0
    squeeze=required and ps<=0 and fs<=0 and bs<0 and os>0 and cs>0 and vs<0
    if trap: score=-max(4.0,abs(score))
    elif squeeze: score=max(4.0,abs(score))
    components['trap_override']=score-sum(components.values())
    context=sequence_context(market,cutoff,m)
    if strategy=='sequence_candidate': score+=context['modifier']
    components['sequence']=context['modifier'] if strategy=='sequence_candidate' else 0.0
    if price is None:
        direction='UNAVAILABLE'; state='AWAITING_CONTIGUOUS_PRICE_HISTORY'; quality['status']='UNAVAILABLE'
    else:
        if score==0:
            score=float(ps or fs or bs or cs or -vs or 1)*.1
            components['tie_break']=score
        direction='UP' if score>0 else 'DOWN'; state='UP_PRESSURE' if direction=='UP' else 'DOWN_PRESSURE'
        if trap and direction=='DOWN': state='LONG_TRAP_RISK'
        elif squeeze and direction=='UP': state='SHORT_SQUEEZE_RISK'
        elif direction=='UP' and ps>0 and os>0 and cs>0 and vs<0: state='AGGRESSIVE_LONG'
        elif direction=='DOWN' and ps<0 and os>0 and cs<0 and vs>0: state='AGGRESSIVE_SHORT'
        elif direction=='UP' and ps>0 and os<0: state='SHORT_COVERING_RALLY'
        elif direction=='DOWN' and ps<0 and os<0: state='LONG_UNWINDING_DECLINE'
        elif direction=='UP' and ps>0 and os>0 and bs>0 and cash is not None and vix is not None and cs<=0 and vs<=0: state='FUTURES_LED_LONG'
        elif direction=='DOWN' and ps<0 and os>0 and bs<0 and cash is not None and vix is not None and cs>=0 and vs>=0: state='FUTURES_LED_SHORT'
        if strategy=='sequence_candidate' and context['episode']!='NO_ORDERED_PATTERN': state='SEQUENCE_'+context['episode']
    vpoc,read=_vpoc_modifier(bundle,direction,float(m['index'])) if direction!='UNAVAILABLE' else (0.0,'Unavailable')
    strength=abs(score)+vpoc; confidence='HIGH' if strength>=7 else 'MEDIUM' if strength>=4 else 'LOW'
    if not complete: confidence='LOW'
    drivers=[f'{label} {m[key]:+.4f}' if m[key] is not None else f'{label} unavailable' for label,key in
             [('Index 5m','index_change_5m'),('Futures 5m','futures_change_5m'),('Basis 5m','basis_change_5m'),('OI 5m','futures_oi_change_5m'),('Cash slope','cash_rolling_change'),('VIX slope','vix_rolling_change')]]
    if strategy=='sequence_candidate': drivers += [f'Structure: {context["session_context"]}',f'Ordered episode: {context["episode"]}']
    level=context['invalidation_level'] if strategy=='sequence_candidate' else None
    if level is not None and ((direction=='UP' and level>=m['index']) or (direction=='DOWN' and level<=m['index']) or direction=='UNAVAILABLE'):
        level=None
    invalidation=(f'Five-minute call invalidates on a completed-minute close {"above" if direction=="DOWN" else "below"} {level:,.2f}.'
                  if level is not None else 'Reassess when the five-minute impulse reverses; no fixed price invalidation is established.')
    result={'schema':'NIFTY_AGGRESSIVE_DIRECTION_V2','classification':'EXPERIMENTAL_DIRECTION_NOT_VALIDATED',
            'causal_as_of':iso_utc(cutoff),'input_cutoff':iso_utc(cutoff),'published_at':iso_utc(published),'t':iso_utc(published),
            'availability_clock':'COMPLETED_MINUTE_PLUS_8_SECONDS','last_price_receipt':market[-1]['t'],'horizon_minutes':5,
            'direction':direction,'state':state,'confidence':confidence,'core_score':round(score,4),'score':round(score,4),
            'vpoc_modifier':vpoc,'vpoc_role':'CONFIDENCE_MODIFIER_ONLY','headline':f'{direction} · {state.replace("_"," ")}',
            'drivers':drivers,'vpoc_read':read,'invalidation':invalidation,'metrics':m,'components':components,'context':context,
            'quality':quality,'strategy':strategy,'aggressive':True}
    digest=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result['decision_id']=f'1.0.62:{digest[:24]}'
    return result


def decision_bundles(market_rows,oi_rows,cash_vix_rows,intraday_rows,*,through=None):
    market=_rows([dict(r) for r in market_rows]); oi=_rows([dict(r) for r in oi_rows])
    cash=_rows([dict(r) for r in cash_vix_rows]); inventory=_rows([dict(r) for r in intraday_rows])
    if not market: return
    through=parse_instant(through) if through is not None else market[-1]['_instant']
    mt=[r['_instant'] for r in market]; ot=[r['_instant'] for r in oi]; ct=[r['_instant'] for r in cash]
    minutes=sorted({t.replace(second=0,microsecond=0) for t in mt})
    history=defaultdict(list); controls={}; cursor=0
    for minute in minutes:
        local=minute.astimezone(IST)
        if (local.hour,local.minute)<(9,45) or (local.hour,local.minute)>=(15,30): continue
        cutoff=minute+timedelta(minutes=1); publication=cutoff+timedelta(seconds=8)
        if publication>through: break
        end=bisect_left(mt,cutoff); begin=bisect_left(mt,cutoff-timedelta(minutes=61))
        oe=bisect_left(ot,cutoff); ce=bisect_right(ct,publication)
        while cursor<len(inventory) and inventory[cursor]['_instant']<cutoff:
            row=inventory[cursor]; family=str(row.get('family',''))
            if family:
                controls[family]={'receipt':row['t'],'control_value':row.get('control_value')}; history[family].append(controls[family])
            cursor+=1
        yield {'recent_market':market[begin:end],'recent_futures_oi':oi[max(0,oe-65):oe],
               'recent_cash_vix':cash[max(0,ce-65):ce],'visible_intraday_inventory':dict(controls),
               'recent_intraday_inventory_shifts':{k:v[-3:] for k,v in history.items()},
               'input_cutoff':iso_utc(cutoff),'decision_at':iso_utc(publication)}


def prediction_series(market_rows,oi_rows,cash_vix_rows,intraday_rows,*,through=None,strategy=None):
    result=[]; previous=None
    for bundle in decision_bundles(market_rows,oi_rows,cash_vix_rows,intraday_rows,through=through):
        prediction=predict_direction(bundle,strategy=strategy); prediction['previous_direction']=previous
        prediction['change_reason']=('First available decision' if previous is None else 'Direction unchanged'
            if previous==prediction['direction'] else f'{previous} → {prediction["direction"]}: '+ '; '.join(prediction['drivers']))
        result.append(prediction); previous=prediction['direction']
    return result

"""Repository-native frozen lifecycle/resolution execution over raw frames."""
from __future__ import annotations

import hashlib
import pandas as pd

from .engine import classify_resolution


def iso(value):return "" if pd.isna(value) else pd.Timestamp(value).isoformat()


def response(episode,index_receipts,limit):
    confirmation=pd.Timestamp(episode["confirmation_timestamp"])
    # The standalone Index response clock is intentionally independent of the
    # synchronized-Basis lifecycle cutoff.  The cutoff is applied only when a
    # response is admitted into the lifecycle transition stream below.
    path=index_receipts[(index_receipts.t>confirmation)&index_receipts["index"].notna()]
    sign=1 if episode["colour"]=="GREEN" else -1
    movement=sign*(path["index"]-float(episode["index_at_confirmation"]))
    favourable=path[movement>=10]; adverse=path[movement<=-10]
    ft=favourable.t.iloc[0] if len(favourable) else pd.NaT; at=adverse.t.iloc[0] if len(adverse) else pd.NaT
    ordering="FAVOURABLE_FIRST" if pd.notna(ft) and (pd.isna(at) or ft<at) else "ADVERSE_FIRST" if pd.notna(at) and (pd.isna(ft) or at<ft) else "AMBIGUOUS" if pd.notna(ft) and ft==at else "UNRESOLVED"
    return {"first_favourable_timestamp":iso(ft),"first_adverse_timestamp":iso(at),"ordering":ordering}


def mechanism_state(mechanism):
    return {"INDEX_CATCH_UP":"INDEX_CATCH_UP","INDEX_CATCH_DOWN":"INDEX_CATCH_DOWN","FUTURES_REVERSED_TO_INDEX":"FUTURES_REVERTING_TO_INDEX","BOTH_CONVERGING_CONSTRUCTIVELY":"BOTH_CONVERGING","BOTH_CONVERGING_ADVERSELY":"BOTH_CONVERGING","BASIS_EXPANSION_CONTINUING":"PERSISTING_OR_EXPANDING","BASIS_EXTREME_STALLED":"WAITING_FOR_PRICE_RESPONSE","UNRESOLVED":"WAITING_FOR_PRICE_RESPONSE"}[mechanism]


def build_lifecycle(episodes,groups,series_by_date,index_by_date):
    group={row["episode_id"]:row for row in groups}; ledger=[]; dense=[]; responses=[]
    by_date={date:sorted([e for e in episodes if e["evaluation_date"]==date],key=lambda e:pd.Timestamp(e["confirmation_timestamp"])) for date in series_by_date}
    group_end={}
    for date,items in by_date.items():
        ids=list(dict.fromkeys(group[e["episode_id"]]["dependency_group_id"] for e in items))
        for i,gid in enumerate(ids):
            next_episode=next((e for e in items if i+1<len(ids) and group[e["episode_id"]]["dependency_group_id"]==ids[i+1]),None)
            group_end[gid]=pd.Timestamp(next_episode["candidate_start_timestamp"]) if next_episode else pd.Timestamp(date+"T15:30:00+05:30")
    for episode in sorted(episodes,key=lambda e:pd.Timestamp(e["confirmation_timestamp"])):
        date=episode["evaluation_date"]; confirmation=pd.Timestamp(episode["confirmation_timestamp"]); items=by_date[date]
        opposite=min([pd.Timestamp(e["confirmation_timestamp"]) for e in items if pd.Timestamp(e["confirmation_timestamp"])>confirmation and e["colour"]!=episode["colour"]],default=pd.Timestamp(date+"T15:30:00+05:30"))
        lifecycle_end=group_end[group[episode["episode_id"]]["dependency_group_id"]]; limit=min(lifecycle_end,opposite)
        observed=response(episode,index_by_date[date],limit);responses.append({"episode_id":episode["episode_id"],**observed})
        path=series_by_date[date][(series_by_date[date].t>confirmation)&(series_by_date[date].t<=limit)&series_by_date[date].validity_status.eq("VALID")]
        emitted=[]; previous="NEUTRAL"; ordinal=0; running=float(episode["basis_at_confirmation"]); last_extreme=confirmation
        def emit(state,t,reason,row=None):
            nonlocal previous,ordinal
            if emitted and emitted[-1]["state"]==state:return
            ordinal+=1; record_id="R6B2R-"+hashlib.sha256(f"{episode['episode_id']}|{iso(t)}|{state}|{ordinal}".encode()).hexdigest()[:20].upper()
            if emitted:emitted[-1]["state_exit_timestamp"]=iso(t)
            emitted.append({"record_id":record_id,"evaluation_date":date,"episode_id":episode["episode_id"],"dependency_group_id":group[episode["episode_id"]]["dependency_group_id"],"colour":episode["colour"],"state":state,"previous_state":previous,"state_entry_timestamp":iso(t),"state_exit_timestamp":"","causal_input_cutoff":iso(t),"reason_code":reason});previous=state
        emit("DIVERGENCE_DETECTED",confirmation,"RAW_LOCKED_CONFIRMATION")
        if group[episode["episode_id"]]["retrigger_flag"]:emit("RETRIGGER_EXISTING_HYPOTHESIS",confirmation,"RAW_DEPENDENT_RETRIGGER")
        timed=[]
        adverse_time=pd.Timestamp(observed["first_adverse_timestamp"]) if observed["first_adverse_timestamp"] else None
        favourable_time=pd.Timestamp(observed["first_favourable_timestamp"]) if observed["first_favourable_timestamp"] else None
        if adverse_time is not None and adverse_time<=limit:timed.append((adverse_time,"ADVERSE_FIRST"))
        if favourable_time is not None and favourable_time<=limit:timed.append((favourable_time,"FAVOURABLE_RESPONSE"))
        event_index=0;timed.sort()
        for _,row in path.iterrows():
            while event_index<len(timed) and timed[event_index][0]<=row.t:emit(timed[event_index][1],timed[event_index][0],"RAW_10_POINT_RESPONSE",row);event_index+=1
            current=round(float(row.basis),2);is_new=current>=round(running,2) if episode["colour"]=="GREEN" else current<=round(running,2)
            if is_new:running=current;last_extreme=row.t
            stalled=(row.t-last_extreme).total_seconds();result=classify_resolution(episode["colour"],float(episode["index_at_confirmation"]),float(episode["futures_at_confirmation"]),float(row["index"]),float(row["futures"]),stalled)
            state=mechanism_state(result.mechanism);emit(state,row.t,"RAW_BASIS_MECHANISM_"+result.mechanism,row)
            dense.append({"episode_id":episode["episode_id"],"evaluation_date":date,"timestamp":iso(row.t),"source_clock":"SYNCHRONIZED_BASIS_CLOCK","initial_index":episode["index_at_confirmation"],"current_index":row["index"],"initial_futures":episode["futures_at_confirmation"],"current_futures":row["futures"],"initial_basis":episode["basis_at_confirmation"],"current_basis":row["basis"],"delta_index":result.index_movement,"delta_futures":result.futures_movement,"delta_basis":result.basis_change,"index_contribution":result.index_contribution,"futures_contribution":result.futures_contribution,"signed_basis_convergence":result.signed_convergence,"new_extreme_flag":is_new,"running_extreme":running,"last_extreme_timestamp":iso(last_extreme),"stalled_extreme_duration_seconds":stalled,"resolution_mechanism_native":result.mechanism,"resolution_mechanism_compatibility":result.compatibility_label,"index_receipt_timestamp":iso(row.index_receipt_timestamp),"futures_receipt_timestamp":iso(row.futures_receipt_timestamp),"synchronization_age_ms":row.absolute_receipt_difference_ms,"validity_status":row.validity_status,"availability_timestamp":iso(row.t)})
        while event_index<len(timed):emit(timed[event_index][1],timed[event_index][0],"RAW_10_POINT_RESPONSE");event_index+=1
        if opposite<=lifecycle_end and opposite<pd.Timestamp(date+"T15:30:00+05:30"):emit("OPPOSITE_DIVERGENCE",opposite,"RAW_OPPOSITE_CONFIRMATION")
        elif not observed["first_favourable_timestamp"]:emit("EXPIRED_OR_UNRESOLVED",lifecycle_end,"LIFECYCLE_END_WITHOUT_FAVOURABLE_RESPONSE")
        ledger.extend(emitted)
    return ledger,dense,responses

"""Frozen dependency/retrigger grouping for raw divergence episodes."""
from __future__ import annotations

import pandas as pd


def group_episodes(episodes, series_by_date):
    rows=[]; previous=None; group_id=None; group_number=0; member=0
    ordered=sorted(episodes,key=lambda x:(x["evaluation_date"],pd.Timestamp(x["confirmation_timestamp"])))
    for episode in ordered:
        new=True; reason="FIRST_SESSION_EPISODE"; complete=True; gap=None; favourable=False; adverse=False; opposite=False
        if previous and previous["evaluation_date"]==episode["evaluation_date"]:
            same=previous["colour"]==episode["colour"]
            gap=(pd.Timestamp(episode["candidate_start_timestamp"])-pd.Timestamp(previous["episode_end_timestamp"])).total_seconds()
            frame=series_by_date[episode["evaluation_date"]]
            between=frame[(frame.t>pd.Timestamp(previous["episode_end_timestamp"]))&(frame.t<pd.Timestamp(episode["candidate_start_timestamp"]))]
            direction=1 if previous["colour"]=="GREEN" else -1
            movement=direction*(between["index"]-float(previous["index_at_confirmation"])) if len(between) else pd.Series(dtype=float)
            favourable=bool(len(movement) and movement.max()>=10); adverse=bool(len(movement) and movement.min()<=-10); opposite=not same
            if same and gap<=300:
                neutral=bool(len(between) and between.candidate_state.eq("NEUTRAL_BLUE").all())
                left=bool(len(between) and (((between.basis_expanding_percentile<.8)&(between.basis_robust_z<1)).any() if previous["colour"]=="GREEN" else ((between.basis_expanding_percentile>.2)&(between.basis_robust_z>-1)).any()))
                complete=bool(gap>=60 and neutral and left and favourable); new=complete
                reason="COMPLETE_RESET" if complete else "BRIEF_INTERRUPTION_NO_COMPLETE_RESET"
            elif same: reason="SAME_COLOUR_GAP_EXCEEDS_300_SECONDS"
            else: reason="OPPOSITE_COLOUR_REVERSAL"
        if new:
            group_number+=1; group_id=f"HYP-{episode['evaluation_date']}-{group_number:03d}-{episode['colour']}"; member=1
        else: member+=1
        root=next((x["episode_id"] for x in rows if x["dependency_group_id"]==group_id),episode["episode_id"])
        rows.append({"dependency_group_id":group_id,"root_episode_id":root,"episode_id":episode["episode_id"],"previous_episode_id":previous["episode_id"] if previous and previous["evaluation_date"]==episode["evaluation_date"] else "","gap_seconds":gap,"favourable_response_before_retrigger":favourable,"adverse_response_before_retrigger":adverse,"opposite_episode_before_retrigger":opposite,"previous_hypothesis_resolved":complete,"classification":"DEPENDENT_RETRIGGER" if member>1 else "NEW_INDEPENDENT_HYPOTHESIS","reason_code":reason,"member_number":member,"retrigger_flag":member>1})
        previous=episode
    return rows

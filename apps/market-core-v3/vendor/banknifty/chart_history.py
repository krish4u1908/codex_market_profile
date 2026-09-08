"""Descriptive morning chart history. Never creates or revises live calls."""
import collections
import analyze as a


def build_chart_history(day, through, inputs, selection):
    start = a.ts(day+'T09:45:00+05:30')
    through = min(through, a.ts(day+'T15:30:00+05:30'))
    inventory = a.Series(inputs['inventory'])
    canonical = a.Series([r for r in inventory.rows
                          if r.get('family') == 'BN_REF_FUT_VOLUME_VPOC'])
    volume = a.Series(inputs['volume'])
    contributions = a.Series([r for r in volume.rows if r.get('vs') == 'VALID'
        and a.finite(r.get('i')) and a.finite(r.get('dv')) and r['dv'] > 0
        and r['_t'] >= start])
    contracts = collections.defaultdict(list)
    for r in inputs['options']:
        contracts[r['symbol']].append(r)
    options = {k:a.Series(v) for k,v in contracts.items()}
    cash = {}
    for r in inputs['cash']:
        # Plot the completed source minute, not the later startup observation.
        boundary = a.ts(r['minute_ist']) + 60
        if boundary <= through:
            cash[boundary] = r
    rows = []
    for cutoff in range(int(start), int(through)+1, 60):
        row = dict(t=a.isot(cutoff), history_origin='RECONSTRUCTED_INPUT_HISTORY')
        j = canonical.before(cutoff)
        if j >= 0 and a.finite(canonical.rows[j].get('control_value')):
            row['volume_cumulative_mode_canonical'] = canonical.rows[j]['control_value']
        w = volume.window(cutoff, 15, 15, 60)
        if cutoff-start >= 900 and w and not any(r.get('vs') in ('GAP_RESET','BASELINE') for r in w[1:]):
            lo = contributions.before(cutoff-900)+1
            hi = contributions.before(cutoff)+1
            mode = a.mode(contributions.rows[lo:hi])
            if mode is not None:
                row['volume_recent_15m_mode'] = mode
        r = cash.get(cutoff)
        if r:
            row['cash_first_observed_at'] = r.get('first_observed_at', r['t'])
            row['cash_source_minute'] = r['minute_ist']
            if (a.finite(r.get('cash_weighted_pct')) and r.get('expected_constituent_count',0)>0
                    and r.get('cash_names') == r['expected_constituent_count']):
                row['cash_raw'] = r['cash_weighted_pct']
            if a.finite(r.get('vix_close')) and r['vix_close'] > 0:
                row['vix_raw'] = r['vix_close']
        features = a.option_features(options, selection, cutoff)
        for key in ('ce_oi_delta_5m', 'pe_oi_delta_5m'):
            if key in features:
                row[key] = features[key]
        rows.append(row)
    return rows

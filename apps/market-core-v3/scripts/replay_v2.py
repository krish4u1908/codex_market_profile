"""Historical V2 envelope using the frozen NIFTY feature functions.

The converter inherited from the September 7 replay utility is retained here;
reference calls use the explicit completed-minute +8s simulation clock.
"""
import collections
from datetime import date
VERSION = '2.0.0'
REQUIRED = ('index_change_5m', 'basis_change_5m', 'futures_oi_change_5m',
            'cash_raw_change_5m', 'vix_raw_change_5m', 'ce_oi_delta_5m',
            'pe_oi_delta_5m', 'volume_recent_15m_mode')
def day_value(value):
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError('Expected YYYY-MM-DD')
    return day

def build_gui(payload, a, predictor):
    """No live runtime, wallclock publication, future outcomes, or score tuning."""
    day = payload['session']
    day_value(day)
    blocks = {k: a.unpack(payload.get(k, {'fields': [], 'rows': []}))
              for k in ('price', 'futures_oi', 'futures_volume', 'option_strike_oi',
                        'intraday_inventory', 'cash_vix')}
    prices, oi = blocks['price'], blocks['futures_oi']
    if not prices:
        raise ValueError('No synchronized NIFTY prices: ' + day)
    for kind, rows in blocks.items():
        if any(a.ist(r['_t'])[:10] != day for r in rows):
            raise ValueError('Cross-session timestamps in ' + kind)
    if any(not a.finite(r.get('i')) or not a.finite(r.get('b')) for r in prices):
        raise ValueError('Non-finite price or basis in source')
    cash = blocks['cash_vix']
    for r in cash:
        r['_minute'] = a.ts(r['minute_ist'])
    cash.sort(key=lambda r: (r['_minute'], r['_t']))
    option_series = collections.defaultdict(list)
    for r in blocks['option_strike_oi']:
        option_series[r['symbol']].append(r)
    option_series = {k: a.Series(v) for k, v in option_series.items()}
    selection = payload.get('option_strike_oi', {}).get('strike_selection', {})
    series = {k: a.Series(v) for k, v in blocks.items()}
    contributions = a.Series([r for r in blocks['futures_volume']
                              if r.get('vs') == 'VALID' and a.finite(r.get('i'))
                              and a.finite(r.get('dv')) and r['dv'] > 0])
    states = a.price_states(prices, day)
    # The +8-second clock is a historical simulation, never an observed live receipt.
    # Do not extrapolate beyond the last available market receipt.
    calls = predictor.prediction_series(prices, oi, cash, blocks['intraday_inventory'],
                                        strategy='corrected')
    decisions = []
    for call in calls:
        cutoff = a.ts(call['input_cutoff'])
        pub = a.ts(call['published_at'])
        j = series['price'].before(cutoff)
        if j < 0 or cutoff - series['price'].t[j] > 15:
            continue
        state = states.get(cutoff, {})
        features = dict(session=day, t=a.isot(pub), ist=a.ist(pub),
                        input_cutoff=a.isot(cutoff), publication_kind='HISTORICAL_SIMULATION',
                        corrected_direction=call['direction'],
                        corrected_score=call.get('core_score', call.get('score')),
                        baseline_note='Reconstructed historical reference call; simulated completed-minute +8s timing.',
                        short_leg=state.get('short', 0), broader_leg=state.get('broad', 0),
                        price_segment=state.get('segment'), index=prices[j]['i'],
                        baseline_quality=call.get('quality', {}))
        features.update(a.cash_features(cash, cutoff, pub))
        features.update(a.option_features(option_series, selection, cutoff))
        features.update(a.volume_features(series['futures_volume'], contributions,
                                         cutoff, blocks['intraday_inventory']))
        for key, kind, field, age, gap in (
                ('index_change_5m', 'price', 'i', 15, 60),
                ('basis_change_5m', 'price', 'b', 15, 60),
                ('futures_oi_change_5m', 'futures_oi', 'oi', 90, 90)):
            w = series[kind].window(cutoff, 5, age, gap)
            features[key] = (w[-1][field] - w[0][field]
                             if w and all(a.finite(r.get(field)) for r in w) else None)
        if a.finite(features.get('fixed_atm')):
            features['index_minus_fixed_atm'] = features['index'] - features['fixed_atm']
        features['missing_inputs'] = [k for k in REQUIRED if not a.finite(features.get(k))]
        features['complete'] = not features['missing_inputs']
        decisions.append(features)
    if not decisions:
        raise ValueError('No completed-minute replay decisions can be built: ' + day)
    minutes = {}
    last_cutoff = a.ts(decisions[-1]['input_cutoff'])
    for row in prices:
        boundary = int(row['_t'] // 60) * 60 + 60
        if boundary > last_cutoff or boundary - row['_t'] > 15:
            continue
        j = series['futures_oi'].before(boundary)
        current_oi = (oi[j].get('oi') if j >= 0 and boundary - oi[j]['_t'] <= 90 else None)
        minutes[boundary] = dict(t=a.isot(boundary), index=row['i'], basis=row['b'],
                                 futures_oi=current_oi)
    warnings = []
    if not blocks['futures_volume']:
        warnings.append('No retained futures-volume observations: yellow and pink volume VPOC lines are unavailable.')
    if not cash:
        warnings.append('No usable Cash/VIX sample block; these inputs remain unavailable.')
    missing = collections.Counter(k for d in decisions for k in d['missing_inputs'])
    coverage = dict(decisions=len(decisions), complete_decisions=sum(d['complete'] for d in decisions),
                    first_decision=decisions[0]['ist'], last_decision=decisions[-1]['ist'],
                    price_minutes=len(minutes), source_rows={k: len(v) for k, v in blocks.items()},
                    missing_input_decisions=dict(missing),
                    yellow_vpoc_decisions=sum(a.finite(d.get('volume_cumulative_mode_canonical')) for d in decisions),
                    pink_vpoc_decisions=sum(a.finite(d.get('volume_recent_15m_mode')) for d in decisions),
                    warnings=warnings)
    return dict(version=VERSION, baseline_version='1.0.62', instrument='NIFTY50', session=day,
                futures_symbol=payload['summary']['futures_symbol'],
                historical_reconstruction=True, decisions=decisions,
                price_history=list(minutes.values()), conversion_coverage=coverage), coverage

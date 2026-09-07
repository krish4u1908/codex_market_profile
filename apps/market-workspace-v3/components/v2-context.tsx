import { ChartPanel, Plot, baseChart, line } from './market-chart';
import { COLORS, clock, compact, fmt, signed, type Frame } from './market-types';

export function V2Context({frame}:{frame:Frame}) {
  const c = frame.context;
  if (!c) return <section className="insight-card"><h2>V2 context</h2><p className="empty-copy">No V2 context has been published at this replay time.</p></section>;
  return <section className="insight-card v2-context">
    <div className="side-heading"><h2>V2 context</h2><span className="mini-label">v2.0.0</span></div>
    <p className="footnote">Published {clock(c.context_published_at || c.t,true)} IST · cutoff {clock(c.input_cutoff,true)} IST</p>
    <div className="v2-metrics">
      <div><span>Index · 5m</span><strong>{signed(c.index_change_5m)}</strong></div>
      <div><span>Basis · 5m</span><strong>{signed(c.basis_change_5m)}</strong></div>
      <div><span>Futures ΔOI · 5m</span><strong>{signed(c.futures_oi_change_5m,0)}</strong></div>
      <div><span>Fixed ATM</span><strong>{fmt(c.fixed_atm,0)}</strong></div>
      <div><span>Short price leg</span><strong>{c.short_leg===1?'Rising':c.short_leg===-1?'Falling':c.short_leg===0?'Flat':'—'}</strong></div>
      <div><span>Broader price leg</span><strong>{c.broader_leg===1?'Rising':c.broader_leg===-1?'Falling':c.broader_leg===0?'Flat':'—'}</strong></div>
    </div>
    <div className="v2-baskets">
      {(['ce','pe'] as const).map(side=><div key={side}>
        <h3>{side.toUpperCase()} basket <small>{c[`${side}_coverage`]??'—'} contracts</small></h3>
        <dl><div><dt>Total OI</dt><dd>{compact(c[`${side}_oi`])}</dd></div>
          <div className="oi-added"><dt>+OI · 5m</dt><dd>{c[`${side}_oi_additions_5m`]==null?'—':`+${compact(c[`${side}_oi_additions_5m`])}`}</dd></div>
          <div className="oi-removed"><dt>−OI · 5m</dt><dd>{c[`${side}_oi_reductions_5m`]==null?'—':`−${compact(c[`${side}_oi_reductions_5m`])}`}</dd></div>
          <div><dt>Net ΔOI · 5m</dt><dd>{signed(c[`${side}_oi_delta_5m`],0)}</dd></div></dl>
      </div>)}
    </div>
    <p className="footnote">These are overlapping five-minute windows. Session cumulative +OI and −OI require individual receipt deltas.</p>
    <p className="source-note">Context inputs: {c.complete?'complete':'incomplete'}{c.missing_inputs?.length?` · ${c.missing_inputs.join(', ').replaceAll('_',' ')}`:''}</p>
  </section>;
}

export function V2FlowCharts({frame,min,max}:{frame:Frame;min:number;max:number}) {
  return <>{(['ce','pe'] as const).map(side=>
    <ChartPanel key={side} title={`${side.toUpperCase()} basket ΔOI`} subtitle="Native V2 · rolling 5m" colour={side==='ce'?COLORS.negative:COLORS.positive}>
      <Plot label={`${side.toUpperCase()} native V2 five-minute net OI change`} height={162} option={{...baseChart(min,max), series:[line(`${side.toUpperCase()} ΔOI · 5m`,frame.contextHistory,`${side}_oi_delta_5m`,side==='ce'?COLORS.negative:COLORS.positive)]}}/>
      {frame.provenance.history_note&&<p className="chart-source-note">{frame.provenance.history_note}</p>}
    </ChartPanel>)}</>;
}

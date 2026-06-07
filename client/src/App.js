import React, {
  useEffect, useRef, useState, useCallback, useMemo
} from 'react';
import BinViewer from './BinViewer';

// ── Global styles injected once ───────────────────────────────────────────────
const GLOBAL_CSS = `
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  * { box-sizing: border-box; }
`;

// ── Shared style tokens ───────────────────────────────────────────────────────
const C = {
  bg0:    '#0f172a',
  bg1:    '#1e293b',
  bg2:    '#0f172a',
  border: '#334155',
  text:   '#f1f5f9',
  muted:  '#94a3b8',
  dim:    '#64748b',
  blue:   '#3b82f6',
  blueL:  '#60a5fa',
  green:  '#34d399',
  amber:  '#f59e0b',
  red:    '#f87171',
  purple: '#a78bfa',
};

const S = {
  app:    { minHeight: '100vh', background: C.bg0, color: C.text, fontFamily: "'Segoe UI', system-ui, sans-serif", padding: '24px 32px' },
  header: { fontSize: 22, fontWeight: 700, marginBottom: 4, color: C.blueL },
  sub:    { fontSize: 13, color: C.muted, marginBottom: 24 },
  card:   { background: C.bg1, borderRadius: 10, padding: '20px 24px', marginBottom: 20 },
  label:  { display: 'block', fontSize: 12, fontWeight: 700, color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' },
  row:    { display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' },
  select: { flex: '1 1 300px', padding: '10px 14px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 6, color: C.text, fontSize: 14 },
  btn:    (dis) => ({ padding: '10px 22px', background: dis ? '#334155' : C.blue, color: dis ? C.dim : '#fff', border: 'none', borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: dis ? 'not-allowed' : 'pointer' }),
  stopBtn: { padding: '10px 22px', background: '#450a0a', color: C.red, border: `1px solid #7f1d1d`, borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  err:    { background: '#450a0a', border: '1px solid #7f1d1d', borderRadius: 6, padding: '12px 16px', color: C.red, fontSize: 13, marginBottom: 16 },
  spinner:{ display: 'inline-block', width: 14, height: 14, border: `2px solid ${C.blue}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite', marginRight: 8, verticalAlign: 'middle' },
  dot:    (on) => ({ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: on ? C.green : C.red, marginRight: 6 }),
};

// ── SVG Convergence Chart ─────────────────────────────────────────────────────
const ConvergenceChart = React.memo(function ConvergenceChart({ data, lowerBound }) {
  if (!data.length) return null;

  const W = 600, H = 120, PAD = { t: 8, r: 12, b: 28, l: 36 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const maxIter = Math.max(...data.map(d => d.iter), 1);
  const allBins = data.map(d => d.bins);
  const minB    = Math.min(...allBins);
  const maxB    = Math.max(...allBins, minB + 1);

  const toX = (iter) => PAD.l + (iter / maxIter) * innerW;
  const toY = (bins) => PAD.t + innerH - ((bins - minB) / (maxB - minB)) * innerH;

  const pts = data.map(d => `${toX(d.iter)},${toY(d.bins)}`).join(' ');

  // Lower bound line y position
  const lbY = lowerBound !== null ? toY(Math.max(lowerBound, minB)) : null;

  // Y-axis tick values
  const yTicks = [minB, Math.round((minB + maxB) / 2), maxB];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`}
         style={{ background: C.bg2, borderRadius: 6, display: 'block' }}>
      {/* Grid lines */}
      {yTicks.map(v => (
        <g key={v}>
          <line x1={PAD.l} y1={toY(v)} x2={W - PAD.r} y2={toY(v)}
                stroke={C.border} strokeWidth={1} strokeDasharray="4 3" />
          <text x={PAD.l - 4} y={toY(v) + 4} textAnchor="end"
                fill={C.dim} fontSize={9}>{v}</text>
        </g>
      ))}
      {/* Lower bound reference line */}
      {lbY !== null && (
        <line x1={PAD.l} y1={lbY} x2={W - PAD.r} y2={lbY}
              stroke={C.green} strokeWidth={1} strokeDasharray="6 3" opacity={0.7} />
      )}
      {/* Data polyline */}
      <polyline points={pts} fill="none" stroke={C.blueL} strokeWidth={2} />
      {/* Last point dot */}
      {data.length > 0 && (
        <circle cx={toX(data.at(-1).iter)} cy={toY(data.at(-1).bins)}
                r={3} fill={C.blueL} />
      )}
      {/* X axis label */}
      <text x={W / 2} y={H - 2} textAnchor="middle" fill={C.dim} fontSize={9}>
        Iteration
      </text>
      {/* Y axis label */}
      <text x={8} y={H / 2} textAnchor="middle" fill={C.dim} fontSize={9}
            transform={`rotate(-90,8,${H / 2})`}>
        Bins
      </text>
      {/* LB legend */}
      {lbY !== null && (
        <text x={W - PAD.r} y={lbY - 3} textAnchor="end" fill={C.green} fontSize={8}>
          LB={lowerBound}
        </text>
      )}
    </svg>
  );
});

// ── Stats table ───────────────────────────────────────────────────────────────
const UDHC_COLORS = { UDHC1: C.blueL, UDHC2: C.green, UDHC3: C.amber, UDHC4: C.red, UDHC5: C.purple };

function StatChip({ label, value, color }) {
  return (
    <div style={{ background: C.bg2, borderRadius: 6, padding: '8px 14px', border: `1px solid ${C.border}`, minWidth: 80 }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || C.blueL }}>{value}</div>
      <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function StatsPanel({ stats, info }) {
  if (!stats && !info) return null;
  const udhcColor = stats ? (UDHC_COLORS[stats.lastUdhc] || C.muted) : C.muted;
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        {info  && <StatChip label="Items"      value={info.n_items}                              color={C.muted} />}
        {info  && <StatChip label="Lower Bound" value={info.lower_bound}                         color={C.green} />}
        {stats && <StatChip label="Bins (best)" value={stats.bins}                               color={C.blueL} />}
        {stats && <StatChip label="Iteration"  value={`${stats.iteration} / ${stats.maxIter}`}  color={C.muted} />}
        {stats && <StatChip label="Temperature" value={stats.temperature}                        color={C.amber} />}
        {stats && <StatChip label="Dissipation" value={stats.dissipation}                        color={C.dim} />}
        {stats && <StatChip label="Score"       value={stats.composite}                          color={C.dim} />}
        {stats && (
          <div style={{ background: C.bg2, borderRadius: 6, padding: '8px 14px', border: `1px solid ${udhcColor}` }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: udhcColor }}>
              {stats.lastUdhc} {stats.udhcAccepted ? '✓' : '✗'}
            </div>
            <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>UDHC operator</div>
          </div>
        )}
      </div>
      {/* Iteration progress bar */}
      {stats && (
        <div style={{ height: 4, background: C.bg2, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${Math.round((stats.iteration / stats.maxIter) * 100)}%`,
            background: `linear-gradient(90deg, ${C.blue}, ${C.blueL})`,
            transition: 'width 0.3s ease',
          }} />
        </div>
      )}
    </div>
  );
}

// ── Final summary panel ───────────────────────────────────────────────────────
function FinalSummary({ result }) {
  if (!result) return null;
  return (
    <div style={{ ...S.card, borderLeft: `3px solid ${C.green}` }}>
      <label style={S.label}>✔ Optimization Complete</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <StatChip label="Bins Used"       value={result.bins_used}             color={C.blueL} />
        <StatChip label="Lower Bound"     value={result.lower_bound}           color={C.green} />
        <StatChip label="Gap from LB"     value={`${result.gap_pct}%`}         color={result.gap_pct === 0 ? C.green : C.amber} />
        <StatChip label="Items Packed"    value={result.n_items}               color={C.muted} />
        <StatChip label="Volume Util."    value={`${result.volume_util_pct}%`} color={C.blueL} />
        <StatChip label="Runtime"         value={`${result.runtime_s}s`}       color={C.muted} />
        <StatChip label="Dissipation"     value={result.dissipation.toFixed(4)} color={C.dim} />
        <StatChip label="Composite Score" value={result.composite_score.toFixed(4)} color={C.dim} />
      </div>
    </div>
  );
}

// ── Loading overlay for the 3-D panel ────────────────────────────────────────
function LoadingOverlay() {
  return (
    <div style={{
      width: '100%', height: '520px', background: '#111827', borderRadius: 8,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 16,
    }}>
      <div style={{ width: 40, height: 40, border: `3px solid ${C.blue}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.9s linear infinite' }} />
      <div style={{ color: C.muted, fontSize: 14 }}>Waiting for first packing data…</div>
    </div>
  );
}

// ── Main Live Runner ──────────────────────────────────────────────────────────
function LiveRunner() {
  const [instances,   setInstances]   = useState([]);
  const [selected,    setSelected]    = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [running,     setRunning]     = useState(false);

  // Optimizer data
  const [instanceInfo, setInstanceInfo] = useState(null); // { container, n_items, lower_bound }
  const [placements,   setPlacements]   = useState(null); // current best solution array
  const [binsUsed,     setBinsUsed]     = useState(0);
  const [chartData,    setChartData]    = useState([]);   // [{iter, bins}] max 100
  const [stats,        setStats]        = useState(null);
  const [finalResult,  setFinalResult]  = useState(null);
  const [error,        setError]        = useState(null);
  const [elapsed,      setElapsed]      = useState(0);

  const wsRef        = useRef(null);
  const reconnectRef = useRef(null);

  // ── WebSocket lifecycle ───────────────────────────────────────────────────
  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'instance_info':
        setInstanceInfo({ container: msg.container, n_items: msg.n_items, lower_bound: msg.lower_bound });
        break;

      case 'iteration_update':
        setPlacements(msg.solution);
        setBinsUsed(msg.best_bins);
        setChartData(prev => {
          const next = [...prev, { iter: msg.iteration, bins: msg.best_bins }];
          return next.length > 100 ? next.slice(-100) : next;
        });
        setStats({
          iteration:    msg.iteration,
          maxIter:      msg.max_iter,
          bins:         msg.best_bins,
          dissipation:  msg.best_dissipation,
          composite:    msg.best_composite,
          temperature:  msg.temperature,
          lastUdhc:     msg.last_udhc,
          udhcAccepted: msg.udhc_accepted,
        });
        break;

      case 'integration_applied':
        // Subtle — stats will update on next iteration_update automatically
        break;

      case 'instance_complete':
        setPlacements(msg.items);
        setBinsUsed(msg.bins_used);
        setFinalResult(msg);
        setRunning(false);
        break;

      case 'stopped':
        setRunning(false);
        break;

      case 'run_closed':
        if (msg.code !== 0) setError(`Optimizer process exited with code ${msg.code}`);
        setRunning(false);
        break;

      case 'error':
        setError(msg.error);
        setRunning(false);
        break;

      default:
        break;
    }
  }, []);

  const connect = useCallback(() => {
    const ws = new WebSocket('ws://localhost:3002');
    wsRef.current = ws;

    ws.onopen  = () => { setWsConnected(true); };
    ws.onclose = () => {
      setWsConnected(false);
      reconnectRef.current = setTimeout(connect, 3000);
    };
    ws.onerror = () => { /* onclose fires next */ };
    ws.onmessage = (e) => {
      try { handleMessage(JSON.parse(e.data)); } catch {}
    };
  }, [handleMessage]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // Keep onmessage fresh when handleMessage reference updates
  useEffect(() => {
    if (wsRef.current) {
      wsRef.current.onmessage = (e) => {
        try { handleMessage(JSON.parse(e.data)); } catch {}
      };
    }
  }, [handleMessage]);

  // ── Elapsed timer ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!running) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  // ── Instance list ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetch('/api/instances')
      .then(r => r.json())
      .then(data => {
        const list = data.instances || [];
        setInstances(list);
        if (list.length) setSelected(list[0].index);
        setLoadingList(false);
      })
      .catch(() => {
        setError('Cannot reach the backend. Is the Node server running on port 3001?');
        setLoadingList(false);
      });
  }, []);

  // ── Controls ──────────────────────────────────────────────────────────────
  const run = useCallback(() => {
    if (selected === undefined || selected === null || running || !wsConnected) return;
    setRunning(true);
    setInstanceInfo(null);
    setPlacements(null);
    setBinsUsed(0);
    setChartData([]);
    setStats(null);
    setFinalResult(null);
    setError(null);
    wsRef.current.send(JSON.stringify({ action: 'run', instanceIndex: selected }));
  }, [selected, running, wsConnected]);

  const stop = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ action: 'stop' }));
  }, []);

  // ── Group and naturally sort instances for <select> ───────────────────────
  const grouped = useMemo(() => {
    const g = {};
    for (const inst of instances) {
      // Extract set from instance ID (e.g., "BR0_1" → "BR0")
      const setName = inst.id?.split('_')[0] || 'Other';
      if (!g[setName]) g[setName] = [];
      g[setName].push(inst);
    }
    
    // Sort items within each set naturally (e.g., BR0_1, BR0_2, BR0_10)
    for (const key of Object.keys(g)) {
      g[key].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
    }

    // Sort the set names naturally (e.g., BR0, BR1, ..., BR10, LN)
    const sortedKeys = Object.keys(g).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const sortedGrouped = {};
    for (const key of sortedKeys) {
      sortedGrouped[key] = g[key];
    }
    
    return sortedGrouped;
  }, [instances]);

  const canRun = wsConnected && !running && (selected !== undefined && selected !== null && selected !== '');

  return (
    <div>
      {/* ── Connection + instance selector ── */}
      <div style={S.card}>
        <label style={S.label}>
          <span style={S.dot(wsConnected)} />
          WebSocket {wsConnected ? 'Connected' : 'Connecting…'}
        </label>
        {loadingList
          ? <span style={{ color: C.muted }}>Loading instances…</span>
          : (
            <div style={S.row}>
              <select
                style={S.select}
                value={selected}
                onChange={e => { setSelected(parseInt(e.target.value, 10)); setFinalResult(null); setPlacements(null); setChartData([]); setStats(null); }}
                disabled={running}
              >
                {Object.entries(grouped).map(([setName, insts]) => (
                  <optgroup key={setName} label={setName}>
                    {insts.map(inst => (
                      <option key={inst.index} value={inst.index}>{inst.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>

              {!running
                ? <button style={S.btn(!canRun)} onClick={run} disabled={!canRun}>
                    ▶  Run Optimizer
                  </button>
                : <>
                    <button style={S.btn(true)} disabled>
                      <span style={S.spinner} />Running… {elapsed}s
                    </button>
                    <button style={S.stopBtn} onClick={stop}>■ Stop</button>
                  </>
              }
            </div>
          )
        }
      </div>

      {/* ── Error ── */}
      {error && <div style={S.err}>⚠ {error}</div>}

      {/* ── Live stats ── */}
      {(stats || instanceInfo) && (
        <div style={S.card}>
          <label style={S.label}>Live Metrics</label>
          <StatsPanel stats={stats} info={instanceInfo} />
        </div>
      )}

      {/* ── 3-D view (immediate on first data) ── */}
      {(running || placements) && (
        <div style={S.card}>
          <label style={S.label}>3-D Packing View</label>
          <p style={{ fontSize: 12, color: C.dim, marginBottom: 12 }}>
            Drag to rotate · Scroll to zoom · Right-drag to pan · Updates every iteration
          </p>
          {placements && instanceInfo
            ? <BinViewer
                placements={placements}
                container={instanceInfo.container}
                binsUsed={binsUsed}
              />
            : <LoadingOverlay />
          }
        </div>
      )}

      {/* ── Convergence chart ── */}
      {chartData.length > 0 && (
        <div style={S.card}>
          <label style={S.label}>Convergence — Bins Used vs Iteration</label>
          <ConvergenceChart data={chartData} lowerBound={instanceInfo?.lower_bound ?? null} />
          <div style={{ fontSize: 11, color: C.dim, marginTop: 6 }}>
            <span style={{ color: C.blueL }}>━</span> Best bins &nbsp;
            <span style={{ color: C.green }}>╌</span> Lower bound
          </div>
        </div>
      )}

      {/* ── Final summary ── */}
      {finalResult && <FinalSummary result={finalResult} />}

      {/* ── Final 3-D view after completion (full result with all items) ── */}
      {finalResult && (
        <div style={S.card}>
          <label style={S.label}>Final Packing</label>
          <p style={{ fontSize: 12, color: C.dim, marginBottom: 12 }}>
            Drag to rotate · Scroll to zoom · Right-drag to pan
          </p>
          <BinViewer
            placements={finalResult.items}
            container={finalResult.container}
            binsUsed={finalResult.bins_used}
          />
        </div>
      )}
    </div>
  );
}

// ── App shell ─────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <div style={S.app}>
      <style>{GLOBAL_CSS}</style>
      <div style={S.header}>STACKR: Structural Three-dimensional Adaptive Constraint-aware pacKing with Routing</div>
      <div style={S.sub}>Bischoff–Ratcliff dataset · BR0–BR18 · Live step-by-step visualisation</div>
      <LiveRunner />
    </div>
  );
}

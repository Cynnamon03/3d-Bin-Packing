import React, { useEffect, useState, useCallback } from 'react';
import BinViewer    from './BinViewer';
import BatchRunner  from './BatchRunner';

const S = {
  app: {
    minHeight: '100vh', background: '#0f172a',
    color: '#f1f5f9', fontFamily: "'Segoe UI', system-ui, sans-serif",
    padding: '24px 32px',
  },
  header: { fontSize: 22, fontWeight: 700, marginBottom: 4, color: '#60a5fa' },
  sub:    { fontSize: 13, color: '#94a3b8', marginBottom: 20 },
  tabs:   { display: 'flex', gap: 4, marginBottom: 20 },
  tab: (active) => ({
    padding: '8px 20px',
    background: active ? '#3b82f6' : '#1e293b',
    color:      active ? '#fff'    : '#94a3b8',
    border: 'none', borderRadius: 6,
    fontSize: 14, fontWeight: 600, cursor: 'pointer',
  }),
  card:  { background: '#1e293b', borderRadius: 10, padding: '20px 24px', marginBottom: 20 },
  label: {
    display: 'block', fontSize: 13, fontWeight: 600,
    color: '#94a3b8', marginBottom: 8,
    textTransform: 'uppercase', letterSpacing: '0.05em',
  },
  row:   { display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' },
  select: {
    flex: '1 1 280px', padding: '10px 14px',
    background: '#0f172a', border: '1px solid #334155',
    borderRadius: 6, color: '#f1f5f9', fontSize: 14,
  },
  btn: (disabled) => ({
    padding: '10px 22px',
    background: disabled ? '#334155' : '#3b82f6',
    color:      disabled ? '#64748b' : '#fff',
    border: 'none', borderRadius: 6,
    fontSize: 14, fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
  }),
  stat: {
    display: 'inline-block', background: '#0f172a',
    borderRadius: 6, padding: '8px 16px',
    marginRight: 10, marginBottom: 8, fontSize: 13,
  },
  statVal: { fontWeight: 700, fontSize: 18, color: '#60a5fa' },
  statLbl: { color: '#94a3b8', marginLeft: 4 },
  err: {
    background: '#450a0a', border: '1px solid #7f1d1d',
    borderRadius: 6, padding: '12px 16px',
    color: '#fca5a5', fontSize: 13, marginBottom: 16,
  },
  spinner: {
    display: 'inline-block', width: 16, height: 16,
    border: '2px solid #3b82f6', borderTopColor: 'transparent',
    borderRadius: '50%', animation: 'spin 0.8s linear infinite',
    marginRight: 8, verticalAlign: 'middle',
  },
};

function SingleRunner() {
  const [instances,   setInstances]   = useState([]);
  const [selected,    setSelected]    = useState('');
  const [loadingList, setLoadingList] = useState(true);
  const [running,     setRunning]     = useState(false);
  const [result,      setResult]      = useState(null);
  const [error,       setError]       = useState(null);
  const [elapsed,     setElapsed]     = useState(0);

  useEffect(() => {
    fetch('/api/instances')
      .then(r => r.json())
      .then(data => {
        setInstances(data.instances || []);
        if (data.instances?.length) setSelected(data.instances[0].path);
        setLoadingList(false);
      })
      .catch(() => {
        setError('Could not reach the backend. Is the Node server running on port 3001?');
        setLoadingList(false);
      });
  }, []);

  useEffect(() => {
    if (!running) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  const run = useCallback(() => {
    if (!selected || running) return;
    setRunning(true); setResult(null); setError(null);
    fetch('/api/run-optimizer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instancePath: selected }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) throw new Error(data.error + '\n' + (data.detail || ''));
        setResult(data); setRunning(false);
      })
      .catch(err => { setError(err.message); setRunning(false); });
  }, [selected, running]);

  const grouped = {};
  for (const inst of instances) {
    if (!grouped[inst.set]) grouped[inst.set] = [];
    grouped[inst.set].push(inst);
  }

  return (
    <div>
      <div style={S.card}>
        <label style={S.label}>Select Instance</label>
        {loadingList ? <span style={{ color: '#94a3b8' }}>Loading…</span> : (
          <div style={S.row}>
            <select style={S.select} value={selected}
              onChange={e => { setSelected(e.target.value); setResult(null); }}
              disabled={running}>
              {Object.entries(grouped).map(([setName, insts]) => (
                <optgroup key={setName} label={setName}>
                  {insts.map(inst => (
                    <option key={inst.path} value={inst.path}>{inst.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
            <button style={S.btn(running)} onClick={run} disabled={running}>
              {running ? <><span style={S.spinner}/>Running… {elapsed}s</> : '▶  Run Optimizer'}
            </button>
          </div>
        )}
      </div>
      {error && <div style={S.err}>⚠ {error}</div>}
      {result && !running && (
        <>
          <div style={S.card}>
            <label style={S.label}>Result</label>
            <span style={S.stat}><span style={S.statVal}>{result.bins_used}</span><span style={S.statLbl}>bins used</span></span>
            <span style={S.stat}><span style={S.statVal}>{result.lower_bound}</span><span style={S.statLbl}>lower bound</span></span>
            <span style={S.stat}><span style={S.statVal}>{result.n_items}</span><span style={S.statLbl}>items</span></span>
            <span style={S.stat}><span style={S.statVal}>{result.dissipation.toFixed(3)}</span><span style={S.statLbl}>dissipation</span></span>
            <span style={S.stat}>
              <span style={S.statVal}>{result.container.L}×{result.container.H}×{result.container.D}</span>
              <span style={S.statLbl}>container</span>
            </span>
          </div>
          <div style={S.card}>
            <label style={S.label}>3-D Packing View</label>
            <p style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
              Drag to rotate · Scroll to zoom · Right-drag to pan
            </p>
            <BinViewer result={result} />
          </div>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState('single');
  return (
    <div style={S.app}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div style={S.header}>3-D Bin Packing — HD-GWO Optimizer</div>
      <div style={S.sub}>Bischoff–Ratcliff dataset · BR0–BR18</div>
      <div style={S.tabs}>
        <button style={S.tab(mode === 'single')} onClick={() => setMode('single')}>Single Instance</button>
        <button style={S.tab(mode === 'batch')}  onClick={() => setMode('batch')}>⚡ Batch Mode (Live)</button>
      </div>
      {mode === 'single' ? <SingleRunner /> : <BatchRunner />}
    </div>
  );
}
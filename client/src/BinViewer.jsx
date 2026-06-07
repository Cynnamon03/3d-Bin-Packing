/**
 * BinViewer.jsx
 * Live 3-D packing visualiser using React Three Fiber.
 *
 * Accepts two equivalent prop shapes:
 *   (A) placements={[{item_idx, bin_id, x, y, z, l, h, d}]}
 *       container={{ L, H, D }}
 *       binsUsed={number}
 *
 *   (B) result={{ items:[...], container:{L,H,D}, bins_used:n }}
 *       (legacy – kept for backward compatibility)
 *
 * Colouring: golden-angle HSL hue per item_idx so every item is visually
 * distinct, even when items of the same type share a bin.
 * Each item gets a thin dark wireframe edge so boxes pop.
 */

import React, { useMemo, useState, useEffect, useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

// ── Per-item colour using golden-angle hue ───────────────────────────────────
function itemHSL(itemIdx) {
  const hue = (itemIdx * 137.508) % 360;
  return `hsl(${hue.toFixed(1)}, 70%, 60%)`;
}

// ── Container wireframe ───────────────────────────────────────────────────────
const WireBox = React.memo(function WireBox({ x, y, z, l, h, d }) {
  const geo = useMemo(() => new THREE.BoxGeometry(l, h, d), [l, h, d]);
  return (
    <lineSegments position={[x + l / 2, y + h / 2, z + d / 2]}>
      <edgesGeometry args={[geo]} />
      <lineBasicMaterial color="white" transparent opacity={0.35} />
    </lineSegments>
  );
});

// ── Packed item: solid face + dark edge outline ───────────────────────────────
const ItemBox = React.memo(function ItemBox({ x, y, z, l, h, d, itemIdx }) {
  const color   = useMemo(() => itemHSL(itemIdx), [itemIdx]);
  const faceGeo = useMemo(() => new THREE.BoxGeometry(l - 1, h - 1, d - 1), [l, h, d]);
  const edgeGeo = useMemo(() => new THREE.EdgesGeometry(faceGeo), [faceGeo]);
  const cx = x + l / 2, cy = y + h / 2, cz = z + d / 2;
  return (
    <group position={[cx, cy, cz]}>
      <mesh geometry={faceGeo}>
        <meshStandardMaterial
          color={color}
          transparent opacity={0.82}
          roughness={0.35} metalness={0.08}
        />
      </mesh>
      <lineSegments geometry={edgeGeo}>
        <lineBasicMaterial color="#000000" transparent opacity={0.55} />
      </lineSegments>
    </group>
  );
});

// ── Main viewer ───────────────────────────────────────────────────────────────
export default function BinViewer({ result, placements: placementsProp, container: containerProp, binsUsed: binsUsedProp }) {
  // Normalise to a single internal format
  const items     = result ? result.items      : (placementsProp || []);
  const container = result ? result.container  : containerProp;
  const binsUsed  = result ? result.bins_used  : (binsUsedProp || 0);

  const [visibleCount, setVisibleCount] = useState(items.length);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState(100);

  // Reset visibleCount to the end of the list when items list changes size
  const lastItemsLength = useRef(items.length);
  useEffect(() => {
    if (items.length !== lastItemsLength.current) {
      setVisibleCount(items.length);
      setIsPlaying(false);
      lastItemsLength.current = items.length;
    }
  }, [items.length]);

  useEffect(() => {
    let timer = null;
    if (isPlaying) {
      timer = setInterval(() => {
        setVisibleCount(prev => {
          if (prev >= items.length) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, playSpeed);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isPlaying, playSpeed, items.length]);

  const togglePlay = () => {
    setVisibleCount(prev => (prev >= items.length ? 0 : prev));
    setIsPlaying(prev => !prev);
  };

  const handleReplay = () => {
    setVisibleCount(0);
    setIsPlaying(true);
  };

  const stepBackward = () => {
    setIsPlaying(false);
    setVisibleCount(prev => Math.max(0, prev - 1));
  };

  const stepForward = () => {
    setIsPlaying(false);
    setVisibleCount(prev => Math.min(items.length, prev + 1));
  };

  const handleSliderChange = (e) => {
    setIsPlaying(false);
    setVisibleCount(parseInt(e.target.value, 10));
  };

  // Group only the VISIBLE items by bin
  const visibleItems = useMemo(() => {
    return items.slice(0, visibleCount);
  }, [items, visibleCount]);

  const byBin = useMemo(() => {
    const m = {};
    for (const it of visibleItems) {
      if (!m[it.bin_id]) m[it.bin_id] = [];
      m[it.bin_id].push(it);
    }
    return m;
  }, [visibleItems]);

  // Group ALL items by bin to compute total containers
  const totalByBin = useMemo(() => {
    const m = {};
    for (const it of items) {
      if (!m[it.bin_id]) m[it.bin_id] = [];
      m[it.bin_id].push(it);
    }
    return m;
  }, [items]);

  if (!container || !items || items.length === 0) return null;

  const { L, H, D } = container;
  const BIN_GAP     = L * 0.12;
  const binCount    = Math.max(binsUsed, ...Object.keys(totalByBin).map(Number)) + 1 || binsUsed;
  const totalWidth  = binCount * L + (binCount - 1) * BIN_GAP;
  const camDist     = Math.max(totalWidth, H, D) * 1.8;

  return (
    <div style={{ width: '100%', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ width: '100%', height: 520, background: '#111827' }}>
        <Canvas
          camera={{ position: [totalWidth / 2, H * 1.2, camDist], fov: 45, far: Math.max(10000, camDist * 3) }}
          gl={{ antialias: true }}
        >
          <ambientLight intensity={0.65} />
          <directionalLight position={[200, 400, 300]} intensity={0.8} />
          <directionalLight position={[-200, 100, -200]} intensity={0.3} />

          {Array.from({ length: binCount }, (_, binId) => {
            const offsetX  = binId * (L + BIN_GAP);
            const binItems = byBin[binId] || [];
            return (
              <group key={binId} position={[offsetX, 0, 0]}>
                <WireBox x={0} y={0} z={0} l={L} h={H} d={D} />
                {binItems.map((it) => (
                  <ItemBox
                    key={it.item_idx}
                    x={it.x} y={it.y} z={it.z}
                    l={it.l} h={it.h} d={it.d}
                    itemIdx={it.item_idx}
                  />
                ))}
              </group>
            );
          })}

          <OrbitControls makeDefault target={[totalWidth / 2, H / 2, D / 2]} />
        </Canvas>
      </div>

      {/* Animation Controls */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 16, padding: '12px 20px',
        background: '#111827', borderTop: '1px solid #374151', borderBottom: '1px solid #374151',
        flexWrap: 'wrap', justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={togglePlay}
            style={{
              background: isPlaying ? '#ef4444' : '#3b82f6',
              color: '#fff', border: 'none', borderRadius: 4,
              padding: '6px 12px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              minWidth: 80
            }}
          >
            {isPlaying ? '❚❚ Pause' : '▶ Play'}
          </button>
          <button
            onClick={handleReplay}
            style={{
              background: '#374151', color: '#f3f4f6', border: 'none', borderRadius: 4,
              padding: '6px 12px', fontSize: 13, cursor: 'pointer'
            }}
          >
            ↺ Replay
          </button>
          <button
            onClick={stepBackward}
            style={{
              background: '#374151', color: '#f3f4f6', border: 'none', borderRadius: 4,
              padding: '6px 10px', fontSize: 13, cursor: 'pointer'
            }}
          >
            ◀
          </button>
          <button
            onClick={stepForward}
            style={{
              background: '#374151', color: '#f3f4f6', border: 'none', borderRadius: 4,
              padding: '6px 10px', fontSize: 13, cursor: 'pointer'
            }}
          >
            ▶
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 200 }}>
          <span style={{ fontSize: 12, color: '#9ca3af', width: 80, textAlign: 'right' }}>
            {visibleCount} / {items.length}
          </span>
          <input
            type="range"
            min={0}
            max={items.length}
            value={visibleCount}
            onChange={handleSliderChange}
            style={{ flex: 1, accentColor: '#3b82f6', cursor: 'pointer' }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#9ca3af' }}>Speed:</span>
          {[50, 100, 250, 500].map(speed => (
            <button
              key={speed}
              onClick={() => setPlaySpeed(speed)}
              style={{
                background: playSpeed === speed ? '#3b82f6' : '#374151',
                color: '#fff', border: 'none', borderRadius: 4,
                padding: '4px 8px', fontSize: 11, cursor: 'pointer'
              }}
            >
              {speed === 50 ? 'Fast' : speed === 100 ? '1x' : speed === 250 ? '0.5x' : '0.2x'}
            </button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex', gap: 14, padding: '8px 16px',
        background: '#1f2937', flexWrap: 'wrap', alignItems: 'center',
      }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>
          {binCount} bin{binCount !== 1 ? 's' : ''} · {items.length} items
        </span>
        {Array.from({ length: Math.min(binCount, 8) }, (_, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{
              width: 12, height: 12, borderRadius: 2, border: '1px solid #374151',
              background: `hsl(${((byBin[i]?.[0]?.item_idx ?? i) * 137.508 % 360).toFixed(0)}, 70%, 60%)`,
            }} />
            <span style={{ color: '#9ca3af', fontSize: 12 }}>
              Bin {i} ({(byBin[i] || []).length})
            </span>
          </div>
        ))}
        {binCount > 8 && (
          <span style={{ color: '#6b7280', fontSize: 12 }}>+ {binCount - 8} more</span>
        )}
      </div>
    </div>
  );
}

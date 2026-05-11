/**
 * BinViewer.jsx
 * 3-D visualisation of bin-packing results using React Three Fiber.
 *
 * Each bin is shown as a white wireframe box.
 * Each packed item is a semi-transparent coloured box.
 * Colours cycle per bin (all items in the same bin share a colour family).
 * OrbitControls let you rotate / zoom with the mouse.
 */

import React, { useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import * as THREE from 'three';

// ── Colour palette: one distinct hue per bin ──────────────────────────────────
const BIN_COLORS = [
  '#4e9af1', '#f1884e', '#6dbf6d', '#c97fd4',
  '#f1d44e', '#4ef1c9', '#f14e7a', '#a0a0ff',
];

function binColor(binId) {
  return BIN_COLORS[binId % BIN_COLORS.length];
}

// ── Wireframe box edges (12 edges of a cuboid) ───────────────────────────────
function WireBox({ x, y, z, l, h, d, color = 'white', opacity = 1 }) {
  // Convert from packing coords (origin at corner) to Three.js (origin at centre)
  const cx = x + l / 2;
  const cy = y + h / 2;
  const cz = z + d / 2;

  return (
    <lineSegments position={[cx, cy, cz]}>
      <edgesGeometry args={[new THREE.BoxGeometry(l, h, d)]} />
      <lineBasicMaterial color={color} transparent opacity={opacity} />
    </lineSegments>
  );
}

// ── Solid semi-transparent item box ──────────────────────────────────────────
function ItemBox({ x, y, z, l, h, d, color }) {
  const cx = x + l / 2;
  const cy = y + h / 2;
  const cz = z + d / 2;

  return (
    <mesh position={[cx, cy, cz]}>
      <boxGeometry args={[l - 1, h - 1, d - 1]} /> {/* 1-unit gap so edges show */}
      <meshStandardMaterial
        color={color}
        transparent
        opacity={0.72}
        roughness={0.4}
        metalness={0.1}
      />
    </mesh>
  );
}

// ── Main viewer ───────────────────────────────────────────────────────────────
export default function BinViewer({ result }) {
  if (!result || !result.items) return null;

  const { container, items, bins_used } = result;
  const { L, H, D } = container;

  // Offset each bin along the X axis so they don't overlap in the view
  const BIN_GAP = L * 0.15;

  // Group items by bin
  const byBin = {};
  for (const item of items) {
    if (!byBin[item.bin_id]) byBin[item.bin_id] = [];
    byBin[item.bin_id].push(item);
  }

  // Camera distance: fit all bins in view
  const totalWidth = bins_used * L + (bins_used - 1) * BIN_GAP;
  const camDist    = Math.max(totalWidth, H, D) * 1.8;

  return (
    <div style={{ width: '100%', height: '520px', background: '#111827', borderRadius: 8 }}>
      <Canvas
        camera={{ position: [totalWidth / 2, H * 1.2, camDist], fov: 45 }}
        shadows
      >
        {/* Lighting */}
        <ambientLight intensity={0.6} />
        <directionalLight position={[200, 400, 300]} intensity={0.8} castShadow />
        <directionalLight position={[-200, 100, -200]} intensity={0.3} />

        {/* Render each bin */}
        {Array.from({ length: bins_used }, (_, binId) => {
          const offsetX = binId * (L + BIN_GAP);
          const color   = binColor(binId);
          const binItems = byBin[binId] || [];

          return (
            <group key={binId} position={[offsetX, 0, 0]}>
              {/* Container wireframe */}
              <WireBox x={0} y={0} z={0} l={L} h={H} d={D}
                       color="rgba(255,255,255,0.5)" opacity={0.5} />

              {/* Packed items */}
              {binItems.map((item) => (
                <ItemBox
                  key={item.item_idx}
                  x={item.x} y={item.y} z={item.z}
                  l={item.l} h={item.h} d={item.d}
                  color={color}
                />
              ))}
            </group>
          );
        })}

        <OrbitControls makeDefault />
      </Canvas>

      {/* Legend */}
      <div style={{
        display: 'flex', gap: 12, padding: '8px 16px',
        background: '#1f2937', borderRadius: '0 0 8px 8px',
        flexWrap: 'wrap',
      }}>
        {Array.from({ length: bins_used }, (_, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: 14, height: 14, borderRadius: 3,
              background: binColor(i), opacity: 0.85,
            }} />
            <span style={{ color: '#d1d5db', fontSize: 13 }}>
              Bin {i} ({(byBin[i] || []).length} items)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
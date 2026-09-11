import { useRef, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Line, Float } from '@react-three/drei';
import * as THREE from 'three';

/* ============================================================
   IntegrityCore — PRAMAAN 3D hero visualization
   Geometric shield/lattice: DATA → MODEL → INFERENCE → AUDIT
   ============================================================ */

type Vec3 = [number, number, number];

// Shield outline points
const SHIELD_POINTS: Vec3[] = [
  [0, 2.2, 0], [-1.4, 1.4, 0], [-1.6, 0.2, 0],
  [-1.2, -0.8, 0], [0, -2.0, 0], [1.2, -0.8, 0],
  [1.6, 0.2, 0], [1.4, 1.4, 0], [0, 2.2, 0],
];

// Layer node positions [DATA layer, MODEL layer, INFERENCE layer, AUDIT]
const NODES: Vec3[] = [
  [-0.7, 1.1, 0], [0.7, 1.1, 0],   // DATA
  [-0.7, 0.3, 0], [0.7, 0.3, 0],   // MODEL
  [-0.7, -0.5, 0], [0.7, -0.5, 0], // INFERENCE
  [0, -1.3, 0],                      // AUDIT
  [0, 2.0, 0],                       // Apex
];

// Pairs of node indices to connect
const CONNECTIONS: [number, number][] = [
  [0, 1], [2, 3], [4, 5],           // horizontal cross-layers
  [0, 2], [1, 3], [2, 4], [3, 5],   // vertical connections
  [4, 6], [5, 6],                    // converge to audit
  [0, 3], [1, 2], [2, 5], [3, 4],   // diagonals
];

function ShieldOutline() {
  return (
    <Line
      points={SHIELD_POINTS}
      color="#3B82F6"
      lineWidth={1}
      transparent
      opacity={0.55}
    />
  );
}

function NodeSphere({ position, size = 0.07 }: { position: Vec3; size?: number }) {
  return (
    <mesh position={position}>
      <sphereGeometry args={[size, 8, 8]} />
      <meshBasicMaterial color="#60A5FA" transparent opacity={0.9} />
    </mesh>
  );
}

function ConnectingLine({ from, to, opacity = 0.28 }: { from: Vec3; to: Vec3; opacity?: number }) {
  return (
    <Line
      points={[from, to]}
      color="#3B82F6"
      lineWidth={0.8}
      transparent
      opacity={opacity}
    />
  );
}

/** Translucent horizontal plane for each layer */
function LayerPlane({ y, opacity = 0.07 }: { y: number; opacity?: number }) {
  return (
    <mesh position={[0, y, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[2.0, 0.5]} />
      <meshBasicMaterial color="#3B82F6" transparent opacity={opacity} side={THREE.DoubleSide} />
    </mesh>
  );
}

function IntegrityCoreScene() {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current) return;
    groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.15) * 0.22;
    groupRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.09) * 0.04;
  });

  return (
    <group ref={groupRef}>
      <ShieldOutline />

      {/* Layer planes */}
      <LayerPlane y={1.1} opacity={0.09} />
      <LayerPlane y={0.3}  opacity={0.07} />
      <LayerPlane y={-0.5} opacity={0.07} />
      <LayerPlane y={-1.3} opacity={0.10} />

      {/* Connections */}
      {CONNECTIONS.map(([a, b], i) => (
        <ConnectingLine
          key={i}
          from={NODES[a]}
          to={NODES[b]}
          opacity={i < 3 ? 0.22 : i < 7 ? 0.30 : 0.15}
        />
      ))}

      {/* Nodes */}
      {NODES.map((pos, i) => (
        <NodeSphere key={i} position={pos} size={i === 7 ? 0.10 : i === 6 ? 0.09 : 0.065} />
      ))}
    </group>
  );
}

/** SVG fallback when WebGL is unavailable */
function SVGFallback() {
  return (
    <svg viewBox="0 0 160 200" className="w-48 h-60 opacity-60" fill="none">
      <path d="M80 8L16 36V96C16 138 44 172 80 184C116 172 144 138 144 96V36L80 8Z"
        stroke="#3B82F6" strokeWidth="1.5" strokeLinejoin="round"/>
      <line x1="40" y1="72" x2="120" y2="72" stroke="#60A5FA" strokeWidth="0.8" opacity="0.6"/>
      <line x1="34" y1="102" x2="126" y2="102" stroke="#60A5FA" strokeWidth="0.8" opacity="0.5"/>
      <line x1="40" y1="132" x2="120" y2="132" stroke="#60A5FA" strokeWidth="0.8" opacity="0.4"/>
      {([
        [56,72],[104,72],[40,102],[120,102],[56,132],[104,132],[80,160],[80,38]
      ] as [number,number][]).map(([cx,cy],i) => (
        <circle key={i} cx={cx} cy={cy} r={i===7?4:3} fill="#60A5FA" opacity="0.85"/>
      ))}
      <line x1="56" y1="72" x2="40" y2="102" stroke="#3B82F6" strokeWidth="0.6" opacity="0.4"/>
      <line x1="104" y1="72" x2="120" y2="102" stroke="#3B82F6" strokeWidth="0.6" opacity="0.4"/>
      <line x1="40" y1="102" x2="56" y2="132" stroke="#3B82F6" strokeWidth="0.6" opacity="0.4"/>
      <line x1="120" y1="102" x2="104" y2="132" stroke="#3B82F6" strokeWidth="0.6" opacity="0.4"/>
      <line x1="56" y1="132" x2="80" y2="160" stroke="#3B82F6" strokeWidth="0.6" opacity="0.4"/>
      <line x1="104" y1="132" x2="80" y2="160" stroke="#3B82F6" strokeWidth="0.6" opacity="0.4"/>
    </svg>
  );
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl') || c.getContext('experimental-webgl'));
  } catch { return false; }
}

export function IntegrityCore({ className }: { className?: string }) {
  if (typeof window === 'undefined' || !hasWebGL()) {
    return <div className={`${className} flex items-center justify-center`}><SVGFallback /></div>;
  }

  return (
    <div className={className}>
      <Canvas
        camera={{ position: [0, 0, 5.5], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
        dpr={[1, 2]}
      >
        <ambientLight intensity={0.6} />
        <Suspense fallback={null}>
          <Float speed={1.2} rotationIntensity={0.08} floatIntensity={0.18}>
            <IntegrityCoreScene />
          </Float>
        </Suspense>
      </Canvas>
    </div>
  );
}

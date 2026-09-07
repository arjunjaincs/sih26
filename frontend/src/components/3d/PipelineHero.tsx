import { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html, MeshDistortMaterial, Sparkles, Edges } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import * as THREE from 'three';

const NODES = [
  { id: 'training', label: 'Training Data', color: '#1F497D', position: [-6.8, 0, 0], scale: 1.15, glow: 0.45 },
  { id: 'model', label: 'Model', color: '#4F81BD', position: [-3.4, 0, 0], scale: 1.15, glow: 0.6 },
  { id: 'inference', label: 'Inference', color: '#4F81BD', position: [0, 0, 0], scale: 1.15, glow: 0.6 },
  { id: 'engine', label: 'Evidence & Risk Engine', color: '#C9A24B', position: [3.4, 0, 0], scale: 1.6, isHighlight: true, glow: 1.25 },
  { id: 'report', label: 'Assurance Report', color: '#1F497D', position: [6.8, 0, 0], scale: 1.15, glow: 0.45 },
];

/**
 * Vertical laser scan sweep — only rendered on the gold highlight node.
 * Uses a single thin ring (no fill disc) to avoid specular starburst artifacts.
 */
function GoldNodeScanner({ scale }: { scale: number }) {
  const scanRingRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const period = 2.6;
    const cycle = (state.clock.elapsedTime % period) / period;
    const yPos = (0.5 - cycle) * 2 * (scale * 1.1);
    const opacity = Math.sin(cycle * Math.PI) * 0.75;

    if (scanRingRef.current) {
      scanRingRef.current.position.y = yPos;
      (scanRingRef.current.material as THREE.MeshBasicMaterial).opacity = opacity;
    }
  });

  return (
    <group>
      {/* Thin ring only — no filled disc to prevent starburst artifacts */}
      <mesh ref={scanRingRef} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[scale * 0.92, scale * 1.01, 48]} />
        <meshBasicMaterial
          color="#C9A24B"
          transparent
          opacity={0.6}
          side={THREE.DoubleSide}
          toneMapped={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

/**
 * Refined scope reticle for the gold differentiator node
 * Thin rings with cardinal tick marks strictly at 12/3/6/9 o'clock
 */
function TargetingReticle({ scale }: { scale: number }) {
  const innerRingRef = useRef<THREE.Group>(null);
  const outerRingRef = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    if (innerRingRef.current) {
      innerRingRef.current.rotation.z += delta * 0.16;
    }
    if (outerRingRef.current) {
      outerRingRef.current.rotation.z -= delta * 0.1;
    }
  });

  const radius = scale * 1.38;

  return (
    <group>
      {/* Primary scope reticle ring with precise 12/3/6/9 o'clock ticks */}
      <group ref={innerRingRef}>
        <mesh>
          <torusGeometry args={[radius, 0.015, 16, 128]} />
          <meshBasicMaterial color="#C9A24B" toneMapped={false} transparent opacity={0.85} />
        </mesh>
        {/* Ticks strictly at 12, 3, 6, 9 o'clock positions */}
        {[Math.PI / 2, 0, (3 * Math.PI) / 2, Math.PI].map((angle, i) => (
          <mesh
            key={i}
            position={[
              Math.cos(angle) * radius,
              Math.sin(angle) * radius,
              0,
            ]}
            rotation={[0, 0, angle]}
          >
            <boxGeometry args={[0.18, 0.025, 0.015]} />
            <meshBasicMaterial color="#FFE68A" toneMapped={false} />
          </mesh>
        ))}
      </group>

      {/* Secondary outer concentric ring */}
      <group ref={outerRingRef} rotation={[Math.PI / 5, Math.PI / 6, 0]}>
        <mesh>
          <torusGeometry args={[radius * 1.15, 0.009, 16, 128]} />
          <meshBasicMaterial color="#C9A24B" toneMapped={false} transparent opacity={0.4} />
        </mesh>
      </group>
    </group>
  );
}

/**
 * Crystalline faceted low-poly node representing verified cryptographic evidence
 */
function PipelineNode({ position, color, label, scale, isHighlight, glow }: any) {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.14;
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.18) * 0.08;
    }
  });

  return (
    <group position={position}>
      {/* Faceted crystalline icosahedron with clean edge geometry */}
      <mesh ref={meshRef} scale={scale}>
        <icosahedronGeometry args={[1, 0]} />
        <MeshDistortMaterial
          color={color}
          emissive={isHighlight ? '#C9A24B' : color}
          emissiveIntensity={glow}
          roughness={0.2}
          metalness={0.65}
          distort={0.05}
          speed={0.5}
          flatShading={true}
          toneMapped={true}
        />
        <Edges
          color={isHighlight ? '#FFE37A' : '#6BA6E8'}
          threshold={10}
          lineWidth={1.2}
        />
      </mesh>

      {/* Gold node only: vertical scan sweep + targeting reticle + subtle point light */}
      {isHighlight && (
        <>
          <GoldNodeScanner scale={scale} />
          <TargetingReticle scale={scale} />
          <pointLight color="#C9A24B" intensity={2.2} distance={7} decay={2.5} />
        </>
      )}

      {/* Unified baseline-aligned military HUD floating label */}
      <Html
        position={[0, -2.45, 0]}
        center
        zIndexRange={[100, 0]}
        distanceFactor={13}
      >
        <div className="relative select-none cursor-default font-mono">
          {/* Identical corner brackets across all 5 nodes */}
          <div className={`absolute -top-1 -left-1 w-2 h-2 border-t-[1.5px] border-l-[1.5px] ${isHighlight ? 'border-pramaan-gold' : 'border-pramaan-steelblue/80'}`} />
          <div className={`absolute -top-1 -right-1 w-2 h-2 border-t-[1.5px] border-r-[1.5px] ${isHighlight ? 'border-pramaan-gold' : 'border-pramaan-steelblue/80'}`} />
          <div className={`absolute -bottom-1 -left-1 w-2 h-2 border-b-[1.5px] border-l-[1.5px] ${isHighlight ? 'border-pramaan-gold' : 'border-pramaan-steelblue/80'}`} />
          <div className={`absolute -bottom-1 -right-1 w-2 h-2 border-b-[1.5px] border-r-[1.5px] ${isHighlight ? 'border-pramaan-gold' : 'border-pramaan-steelblue/80'}`} />

          {/* Unified HUD badge content */}
          <div
            className={`px-3 py-1.5 text-[11px] tracking-widest uppercase flex items-center gap-2 backdrop-blur-md transition-all ${
              isHighlight
                ? 'bg-pramaan-navy/95 border border-pramaan-gold text-pramaan-gold shadow-[0_0_12px_rgba(201,162,75,0.3)] font-bold'
                : 'bg-pramaan-navy/90 border border-pramaan-steelblue/40 text-slate-200'
            }`}
          >
            <span className={`w-1.5 h-1.5 ${isHighlight ? 'bg-pramaan-gold shadow-[0_0_6px_#C9A24B]' : 'bg-pramaan-steelblue'}`} />
            <span>{label}</span>
          </div>
        </div>
      </Html>
    </group>
  );
}

/**
 * Fiber-optic signal connector: a thin glowing tube with a smooth traveling pulse.
 * No hexagons. One continuous elegant line per connection with a moving glow sphere.
 */
function FiberOpticConnector({
  start,
  end,
  isTargetGold,
  chainIndex,
}: {
  start: [number, number, number];
  end: [number, number, number];
  isTargetGold: boolean;
  chainIndex: number;
}) {
  const pulseRef = useRef<THREE.Mesh>(null);
  const vStart = useMemo(() => new THREE.Vector3(...start), [start]);
  const vEnd = useMemo(() => new THREE.Vector3(...end), [end]);

  // Build a straight tube along the line
  const tubeCurve = useMemo(() => {
    return new THREE.LineCurve3(vStart.clone(), vEnd.clone());
  }, [vStart, vEnd]);

  // Animate pulse sphere from start to end on a loop, offset per connector
  useFrame((state) => {
    if (!pulseRef.current) return;
    const speed = 0.45;
    const offset = chainIndex * 0.28;
    const t = ((state.clock.elapsedTime * speed + offset) % 1 + 1) % 1;
    pulseRef.current.position.lerpVectors(vStart, vEnd, t);
  });

  const lineColor = '#C9A24B';
  const pulseColor = isTargetGold ? '#FFF5B0' : '#C8DFFF';

  return (
    <group>
      {/* Outer soft glow tube (slightly larger, very transparent) */}
      <mesh>
        <tubeGeometry args={[tubeCurve, 32, 0.035, 8, false]} />
        <meshBasicMaterial
          color={lineColor}
          transparent
          opacity={0.12}
          toneMapped={false}
          depthWrite={false}
        />
      </mesh>

      {/* Inner precise fiber core */}
      <mesh>
        <tubeGeometry args={[tubeCurve, 32, 0.012, 8, false]} />
        <meshBasicMaterial
          color={lineColor}
          transparent
          opacity={0.75}
          toneMapped={false}
        />
      </mesh>

      {/* Smooth traveling pulse sphere */}
      <mesh ref={pulseRef}>
        <sphereGeometry args={[0.07, 16, 16]} />
        <meshBasicMaterial
          color={pulseColor}
          transparent
          opacity={0.95}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

export default function PipelineHero() {
  return (
    <div className="w-full h-full bg-pramaan-navy relative overflow-hidden" style={{ height: '100vh' }}>
      {/* Radial vignette overlay */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(4,11,21,0.95)_100%)] z-[4]" />

      {/* Subtle bottom-fade gradient so floor grid blends seamlessly into screen edge */}
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-36 bg-gradient-to-t from-[#0B1F3A] via-[#0B1F3A]/70 to-transparent z-[5]" />

      <Canvas
        camera={{ position: [0, 0.2, 14.8], fov: 41 }}
        gl={{
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.05,
          antialias: true,
        }}
      >
        <color attach="background" args={['#060F1D']} />

        {/* Unified Lighting: One coherent Key light from top-left */}
        <directionalLight position={[-9, 14, 8]} intensity={0.95} color="#EAF2FC" />

        {/* Soft fill light from lower-right */}
        <directionalLight position={[8, -5, 5]} intensity={0.2} color="#1F497D" />

        {/* Soft top-back rim for general depth — lowered intensity to eliminate specular starburst */}
        <directionalLight position={[0, 10, -7]} intensity={0.28} color="#4A7AB0" />

        {/* Subtle ambient lighting */}
        <ambientLight intensity={0.3} color="#0B1F3A" />



        {/* Subtle slow drifting dust */}
        <Sparkles
          count={45}
          scale={[26, 10, 16]}
          position={[0, 2, -5]}
          size={1.3}
          speed={0.16}
          opacity={0.18}
          color="#4F81BD"
        />

        {/* Nodes centered vertically at ~48-50% viewport height */}
        <group position={[0, 0.1, 0]}>
          {NODES.map((node) => (
            <PipelineNode key={node.id} {...node} />
          ))}

          {NODES.map((node, i) => {
            if (i === NODES.length - 1) return null;
            const nextNode = NODES[i + 1];
            return (
              <FiberOpticConnector
                key={`${node.id}-fiber`}
                chainIndex={i}
                start={node.position as [number, number, number]}
                end={nextNode.position as [number, number, number]}
                isTargetGold={!!nextNode.isHighlight}
              />
            );
          })}
        </group>

        {/* Tightened crisp bloom pass */}
        <EffectComposer>
          <Bloom
            mipmapBlur
            intensity={1.1}
            luminanceThreshold={0.52}
            luminanceSmoothing={0.25}
          />
        </EffectComposer>

        {/* Smooth OrbitControls */}
        <OrbitControls
          enableZoom={true}
          enablePan={false}
          autoRotate
          autoRotateSpeed={0.25}
          maxPolarAngle={Math.PI / 2 + 0.05}
          minPolarAngle={Math.PI / 2 - 0.4}
          maxDistance={22}
          minDistance={9}
        />
      </Canvas>
    </div>
  );
}

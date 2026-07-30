import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

const PARTICLE_COUNT = 2600
const FIELD_RADIUS = 9

const GRADIENT_STOPS = [
  new THREE.Color('#7C3AED'),
  new THREE.Color('#6366F1'),
  new THREE.Color('#60A5FA'),
]

function sampleGradient(t: number): THREE.Color {
  const scaled = t * (GRADIENT_STOPS.length - 1)
  const index = Math.min(Math.floor(scaled), GRADIENT_STOPS.length - 2)
  const localT = scaled - index
  return GRADIENT_STOPS[index].clone().lerp(GRADIENT_STOPS[index + 1], localT)
}

export function ParticleField() {
  const pointsRef = useRef<THREE.Points>(null)
  const { viewport } = useThree()

  const [positions, colors] = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3)
    const col = new Float32Array(PARTICLE_COUNT * 3)

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const radius = FIELD_RADIUS * Math.cbrt(Math.random())
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)

      pos[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
      pos[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta) * 0.6
      pos[i * 3 + 2] = radius * Math.cos(phi) * 0.6 - 2

      const color = sampleGradient(Math.random())
      col[i * 3] = color.r
      col[i * 3 + 1] = color.g
      col[i * 3 + 2] = color.b
    }

    return [pos, col]
  }, [])

  useFrame((state) => {
    const points = pointsRef.current
    if (!points) return

    const t = state.clock.getElapsedTime()
    points.rotation.y = t * 0.02
    points.rotation.x = Math.sin(t * 0.05) * 0.05

    const targetX = (state.pointer.x * viewport.width) / 60
    const targetY = (state.pointer.y * viewport.height) / 60
    points.position.x += (targetX - points.position.x) * 0.02
    points.position.y += (targetY - points.position.y) * 0.02
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.045}
        vertexColors
        transparent
        opacity={0.85}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  )
}

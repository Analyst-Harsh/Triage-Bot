import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

export function SignalCore() {
  const groupRef = useRef<THREE.Group>(null)
  const coreRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const group = groupRef.current
    const core = coreRef.current
    if (!group || !core) return

    const t = state.clock.getElapsedTime()
    const targetTiltY = t * 0.15 + state.pointer.x * 0.4
    const targetTiltX = Math.sin(t * 0.2) * 0.15 - state.pointer.y * 0.3
    group.rotation.y += (targetTiltY - group.rotation.y) * 0.05
    group.rotation.x += (targetTiltX - group.rotation.x) * 0.05
    const pulse = 1 + Math.sin(t * 1.2) * 0.04
    core.scale.setScalar(pulse)
  })

  return (
    <group ref={groupRef} position={[0, 0, -1]}>
      <mesh ref={coreRef}>
        <icosahedronGeometry args={[1.3, 1]} />
        <meshBasicMaterial color="#7C3AED" transparent opacity={0.14} />
      </mesh>
      <mesh>
        <icosahedronGeometry args={[1.75, 1]} />
        <meshBasicMaterial color="#60A5FA" wireframe transparent opacity={0.35} />
      </mesh>
      <mesh>
        <icosahedronGeometry args={[0.7, 0]} />
        <meshBasicMaterial color="#F8FAFC" transparent opacity={0.9} />
      </mesh>
    </group>
  )
}

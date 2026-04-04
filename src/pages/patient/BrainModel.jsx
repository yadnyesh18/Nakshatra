import React, { useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'

import brainUrl from '../../components/assets/3d-brain.glb?url'

const BrainModel = React.forwardRef(({ scrollYProgress }, ref) => {
  const { scene } = useGLTF(brainUrl)
  const clone = useMemo(() => scene.clone(), [scene])

  useFrame(() => {
    const p = scrollYProgress.current
    
    // Brain is hidden (scale 0) until the cognitive stage (p > 0.66)
    if (p <= 0.66) {
      if (ref.current) {
        ref.current.scale.set(0, 0, 0)
      }
    } else {
      // Scale up from 0 to 1
      const scaleP = (p - 0.66) * 3
      if (ref.current) {
        // use lerp to smooth it out
        const targetScale = scaleP * 1.5 // Max scale factor
        ref.current.scale.lerp({ x: targetScale, y: targetScale, z: targetScale }, 0.1)
        
        // Add a gentle rotation
        ref.current.rotation.y += 0.005
      }
    }
  })

  // Positioned high up corresponding to the head location
  return (
    <group ref={ref} position={[0, 1.7, 0]}>
      <primitive object={clone} />
      
      {/* Small internal glow to make it stand out */}
      <pointLight distance={2} intensity={0.5} color="#4A6FA5" />
    </group>
  )
})

useGLTF.preload(brainUrl)

export default BrainModel

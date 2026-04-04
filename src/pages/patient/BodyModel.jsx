import React, { useRef, useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'

import maleUrl from '../../components/assets/Male.glb?url'
import femaleUrl from '../../components/assets/Female_body.glb?url'

const BodyModel = React.forwardRef(({ scrollYProgress }, ref) => {
  // Let's use Male model by default. In a full implementation, 
  // you'd select maleUrl or femaleUrl based on the user's profile.
  const { scene } = useGLTF(maleUrl)
  
  // Clone scene so we can safely mutate materials
  const clone = useMemo(() => scene.clone(), [scene])
  const injuryNodeRef = useRef()

  useFrame(() => {
    const p = scrollYProgress.current
    
    // Fade body out as we dive to the knee (from 0.33 to 0.66)
    let opacity = 1
    if (p > 0.33) {
       opacity = 1 - ((p - 0.33) * 3)
       if (opacity < 0.1) opacity = 0.1 // Base opacity so it doesn't totally disappear
    }

    clone.traverse((child) => {
      if (child.isMesh) {
        if (!child.userData.materialCloned) {
           child.material = child.material.clone()
           child.material.transparent = true
           child.userData.materialCloned = true
        }
        child.material.opacity = opacity
      }
    })

    // Pulsate the injury node
    if (injuryNodeRef.current) {
       const scale = 1 + Math.sin(Date.now() * 0.005) * 0.2
       injuryNodeRef.current.scale.set(scale, scale, scale)
    }
  })

  // Body origin adjustments:
  // Usually these models center at feet (y=0) or pelvis. 
  // Setting Y to -0.8 places the chest somewhat near the center (Y=0) 
  // so the camera looks at the upper body naturally on load.
  return (
    <group ref={ref} position={[0, -0.8, 0]}>
      <primitive object={clone} />
      
      {/* Injury Node (Right Knee) 
          Coordinates estimated based on standard humanoid scale. */}
      <mesh ref={injuryNodeRef} position={[-0.2, 0.5, 0.05]}>
        <sphereGeometry args={[0.06, 32, 32]} />
        <meshStandardMaterial 
          color="#C47474" 
          emissive="#C47474" 
          emissiveIntensity={2} 
          transparent
          opacity={0.8}
        />
      </mesh>
    </group>
  )
})

// Pre-load the assets
useGLTF.preload(maleUrl)
useGLTF.preload(femaleUrl)

export default BodyModel

import { useEffect, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Environment, ContactShadows, OrbitControls } from '@react-three/drei'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'

import BodyModel from './BodyModel'
import BrainModel from './BrainModel'
import ScrollOverlayUI from './ScrollOverlayUI'

gsap.registerPlugin(ScrollTrigger)

function Scene({ scrollYProgress }) {
  const cameraGroup = useRef()
  const bodyRef = useRef()
  const brainRef = useRef()
  
  useFrame((state) => {
    const progress = scrollYProgress.current

    // -- HERO STAGE (0.0 to 0.33) --
    // Full body orbits automatically. 
    if (progress <= 0.33) {
      if (bodyRef.current) {
        bodyRef.current.rotation.y = state.clock.elapsedTime * 0.5
      }
      state.camera.position.lerp({ x: 0, y: 1, z: 4 }, 0.1)
      state.camera.lookAt(0, 1, 0)
    }

    // -- PHYSICAL STAGE (0.33 to 0.66) --
    // Dive to Right Knee
    if (progress > 0.33 && progress <= 0.66) {
      // Normalize progress within this stage (0 to 1)
      const p = (progress - 0.33) * 3
      if (bodyRef.current) {
        // Stop auto rotation and face forward
        bodyRef.current.rotation.y = gsap.utils.interpolate(bodyRef.current.rotation.y, Math.PI * 2, 0.1) % (Math.PI * 2)
      }
      
      // Move camera to right knee 
      // Approximate coordinates: x: -0.2 (right leg visually left), y: 0.5, z: 1.2
      state.camera.position.lerp({ x: -0.2 * p, y: 1 - (0.5 * p), z: 4 - (2.5 * p) }, 0.1)
      state.camera.lookAt(-0.2, 0.5, 0)
    }

    // -- COGNITIVE STAGE (0.66 to 1.0) --
    // Pan up to Head. 
    if (progress > 0.66) {
      const p = (progress - 0.66) * 3
      state.camera.position.lerp({ x: 0, y: 0.5 + (1.2 * p), z: 1.5 - (0.3 * p) }, 0.1) // moves up to Y=1.7
      state.camera.lookAt(0, 1.7, 0)
    }
  })

  return (
    <group ref={cameraGroup}>
      <ambientLight intensity={0.4} />
      <directionalLight position={[2, 5, 2]} intensity={1.5} color="#C9A84C" />
      <directionalLight position={[-2, 3, 2]} intensity={1.0} color="#4A6FA5" />
      
      <BodyModel ref={bodyRef} scrollYProgress={scrollYProgress} />
      <BrainModel ref={brainRef} scrollYProgress={scrollYProgress} />
      
      <ContactShadows position={[0, -0.01, 0]} opacity={0.4} scale={5} blur={2} far={4} color="#C9A84C" />
      <Environment preset="city" />
    </group>
  )
}

export default function UnifiedDashboard() {
  const containerRef = useRef()
  const scrollYProgress = useRef(0)
  const { user } = useAuthStore()

  useEffect(() => {
    // Setup GSAP ScrollTrigger to update our react ref instantly
    ScrollTrigger.create({
      trigger: containerRef.current,
      start: 'top top',
      end: 'bottom bottom',
      scrub: true,
      onUpdate: (self) => {
        scrollYProgress.current = self.progress
      }
    })

    return () => {
      ScrollTrigger.getAll().forEach(t => t.kill())
    }
  }, [])

  return (
    <div ref={containerRef} className="relative w-full" style={{ height: '300vh', background: '#08090F' }}>
      
      {/* 3D Canvas Layer */}
      <div className="fixed top-0 left-0 w-full h-screen z-0 pointer-events-none">
        <Canvas camera={{ position: [0, 1, 4], fov: 45 }}>
          <Scene scrollYProgress={scrollYProgress} />
        </Canvas>
      </div>

      {/* HTML Overlay Layer */}
      <ScrollOverlayUI user={user} scrollYProgress={scrollYProgress} />
      
    </div>
  )
}

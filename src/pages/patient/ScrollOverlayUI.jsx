import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import GlassCard from '../../components/ui/GlassCard'
import PillButton from '../../components/ui/PillButton'
import MonoChip from '../../components/ui/MonoChip'

export default function ScrollOverlayUI({ user, scrollYProgress }) {
  const navigate = useNavigate()
  const [stage, setStage] = useState(0) // 0: Hero, 1: Physical, 2: Cognitive
  
  useEffect(() => {
    // Check the GSAP progress ref using requestAnimationFrame to sync React state
    let animationFrameId
    
    const checkScroll = () => {
      const p = scrollYProgress.current
      if (p < 0.33 && stage !== 0) {
        setStage(0)
      } else if (p >= 0.33 && p < 0.66 && stage !== 1) {
        setStage(1)
      } else if (p >= 0.66 && stage !== 2) {
        setStage(2)
      }
      animationFrameId = requestAnimationFrame(checkScroll)
    }
    
    checkScroll()
    return () => cancelAnimationFrame(animationFrameId)
  }, [stage, scrollYProgress])

  return (
    <div className="absolute top-0 left-0 w-full h-[300vh] pointer-events-none">
      <div className="sticky top-0 w-full h-screen overflow-hidden flex flex-col justify-center px-8 md:px-24">
        
        {/* Navigation Indicator / Meta Data */}
        <div className="absolute top-8 left-8 pointer-events-auto">
          <MonoChip text={`STAGE: 0${stage + 1} / 03`} color="blue" />
        </div>

        <AnimatePresence mode="wait">
          {/* HERO STAGE */}
          {stage === 0 && (
            <motion.div 
              key="hero"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20, transition: { duration: 0.2 } }}
              transition={{ duration: 0.5 }}
              className="max-w-md pointer-events-auto"
            >
              <h1 style={{ fontFamily: '"Cormorant Garamond", serif', color: '#F0EDE6' }} className="text-5xl md:text-6xl italic font-light mb-4 leading-tight">
                Rehabilitation <br /> <span style={{ color: '#C9A84C' }}>Journey</span>
              </h1>
              <p style={{ fontFamily: '"DM Sans", sans-serif', color: 'rgba(240,237,230,0.6)' }} className="text-lg mb-8 leading-relaxed">
                Scroll to explore your unified recovery roadmap. Your body and mind are monitored in real-time.
              </p>
              <MonoChip text="SCROLL TO DIVE IN ↓" color="gold" />
            </motion.div>
          )}

          {/* PHYSICAL STAGE */}
          {stage === 1 && (
            <motion.div 
              key="physical"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
              transition={{ duration: 0.5 }}
              className="max-w-md pointer-events-auto mt-64 ml-auto right-12 md:right-32 absolute"
            >
              <GlassCard>
                <div className="p-8">
                  <MonoChip text="TARGET AREA" color="red" />
                  <h2 style={{ fontFamily: '"Cormorant Garamond", serif', color: '#F0EDE6' }} className="text-4xl italic font-light mt-4 mb-2">
                    Right Knee
                  </h2>
                  <p style={{ fontFamily: '"DM Sans", sans-serif', color: 'rgba(240,237,230,0.6)' }} className="text-sm mb-6 leading-relaxed">
                    Detected structural fatigue. Session customized to focus on lateral stability and flexion extension.
                  </p>
                  
                  <PillButton 
                    variant="gold" 
                    fullWidth 
                    onClick={() => navigate('/patient/session/physical')}
                  >
                    START PHYSIOTHERAPY
                  </PillButton>
                </div>
              </GlassCard>
            </motion.div>
          )}

          {/* COGNITIVE STAGE */}
          {stage === 2 && (
            <motion.div 
              key="cognitive"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              // Simulating the 2-second delay requested via transition delay
              transition={{ duration: 0.6, delay: 0.5 }}
              exit={{ opacity: 0, y: -30, transition: { duration: 0.2 } }}
              className="max-w-md m-auto pointer-events-auto"
            >
              <GlassCard>
                <div className="p-8 text-center">
                  <div className="flex justify-center mb-4">
                     <MonoChip text="NEURAL SYNCHRONY" color="blue" />
                  </div>
                  <h2 style={{ fontFamily: '"Cormorant Garamond", serif', color: '#F0EDE6' }} className="text-4xl italic font-light mb-2">
                    Cognitive Test
                  </h2>
                  <p style={{ fontFamily: '"DM Sans", sans-serif', color: 'rgba(240,237,230,0.6)' }} className="text-sm mb-6 leading-relaxed">
                    Evaluate processing speed, spatial memory, and reaction time to establish today's baseline.
                  </p>
                  
                  <PillButton 
                    variant="primary" /* Usually mapped to blue accent in standard design */
                    onClick={() => navigate('/patient/session/cognitive')}
                  >
                    BEGIN DIAGNOSTIC
                  </PillButton>
                </div>
              </GlassCard>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </div>
  )
}

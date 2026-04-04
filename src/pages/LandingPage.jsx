import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import GlassCard from '../components/ui/GlassCard'
import PillButton from '../components/ui/PillButton'

// ─────────────────────────────────────────────────────────────
// STARFIELD CANVAS
// ─────────────────────────────────────────────────────────────
function StarfieldCanvas() {
  const canvasRef = useRef(null)
  const mouseRef = useRef({ x: 0.5, y: 0.5 })
  const particlesRef = useRef([])
  const animFrameRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    // Init 200 particles
    particlesRef.current = Array.from({ length: 200 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      radius: Math.random() * 1.2 + 0.3,
    }))

    const draw = () => {
      const w = canvas.width
      const h = canvas.height
      const mx = (mouseRef.current.x - 0.5) * 2
      const my = (mouseRef.current.y - 0.5) * 2

      ctx.clearRect(0, 0, w, h)

      particlesRef.current.forEach(p => {
        // Move
        p.x += p.vx + mx * 0.08
        p.y += p.vy + my * 0.08

        // Wrap edges
        if (p.x < 0) p.x += w
        if (p.x > w) p.x -= w
        if (p.y < 0) p.y += h
        if (p.y > h) p.y -= h

        // Draw
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255,255,255,0.5)'
        ctx.fill()
      })

      animFrameRef.current = requestAnimationFrame(draw)
    }

    draw()

    const onMouseMove = (e) => {
      mouseRef.current = {
        x: e.clientX / window.innerWidth,
        y: e.clientY / window.innerHeight,
      }
    }
    window.addEventListener('mousemove', onMouseMove)

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      window.removeEventListener('resize', resize)
      window.removeEventListener('mousemove', onMouseMove)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  )
}

// ─────────────────────────────────────────────────────────────
// SCROLL CHEVRON
// ─────────────────────────────────────────────────────────────
function ScrollChevron() {
  return (
    <div style={{
      position: 'absolute',
      bottom: '40px',
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 10,
      animation: 'bounceDown 1.5s ease-in-out infinite',
    }}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// STETHOSCOPE ICON
// ─────────────────────────────────────────────────────────────
function StethoscopeIcon() {
  return (
    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="#4A6FA5" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 6v14a12 12 0 0 0 24 0V6" />
      <circle cx="34" cy="30" r="4" />
      <path d="M10 6h4M22 6h4" />
      <circle cx="10" cy="6" r="2" fill="#4A6FA5" />
      <circle cx="26" cy="6" r="2" fill="#4A6FA5" />
      <path d="M34 34v4" />
      <circle cx="34" cy="39" r="1.5" fill="#4A6FA5" />
    </svg>
  )
}

// ─────────────────────────────────────────────────────────────
// PATIENT FIGURE ICON
// ─────────────────────────────────────────────────────────────
function PatientIcon() {
  return (
    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="22" cy="8" r="5" />
      <path d="M22 13v14" />
      <path d="M12 18l10 4 10-4" />
      <path d="M16 27l-4 12" />
      <path d="M28 27l4 12" />
    </svg>
  )
}

// ─────────────────────────────────────────────────────────────
// PROBLEM LINE — IntersectionObserver hook + motion
// ─────────────────────────────────────────────────────────────
function ProblemLine({ text, color = '#F0EDE6', delay = 0, inView }) {
  return (
    <motion.p
      initial={{ opacity: 0, y: 20 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
      transition={{ duration: 0.7, delay, ease: 'easeOut' }}
      style={{
        fontFamily: '"Cormorant Garamond", serif',
        fontStyle: 'italic',
        fontWeight: 300,
        fontSize: 'clamp(32px, 5vw, 60px)',
        color,
        lineHeight: 1.25,
        margin: 0,
      }}
    >
      {text}
    </motion.p>
  )
}

// ─────────────────────────────────────────────────────────────
// PATH CARD
// ─────────────────────────────────────────────────────────────
function PathCard({ icon, title, description, buttonLabel, buttonVariant, onClick }) {
  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -4 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      style={{ flex: 1, minWidth: 0 }}
    >
      <GlassCard>
        <div style={{
          padding: '40px 36px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          gap: 0,
        }}>
          <div style={{ marginBottom: '16px' }}>{icon}</div>

          <h3 style={{
            fontFamily: '"Cormorant Garamond", serif',
            fontStyle: 'italic',
            fontWeight: 300,
            fontSize: '32px',
            color: '#F0EDE6',
            margin: 0,
            lineHeight: 1.2,
          }}>
            {title}
          </h3>

          <p style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '14px',
            color: 'rgba(240,237,230,0.55)',
            margin: '10px 0 28px',
            lineHeight: 1.6,
            maxWidth: '240px',
          }}>
            {description}
          </p>

          <PillButton variant={buttonVariant} onClick={onClick}>
            {buttonLabel}
          </PillButton>
        </div>
      </GlassCard>
    </motion.div>
  )
}

// ─────────────────────────────────────────────────────────────
// MAIN LANDING PAGE
// ─────────────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate = useNavigate()

  // Refs for IntersectionObserver sections
  const problemRef = useRef(null)
  const pathRef = useRef(null)

  const problemInView = useInView(problemRef, { once: true, amount: 0.3 })
  const pathInView = useInView(pathRef, { once: true, amount: 0.3 })

  return (
    <div style={{ background: '#08090F', minHeight: '100vh', position: 'relative' }}>

      {/* ── Bounce keyframe ── */}
      <style>{`
        @keyframes bounceDown {
          0%, 100% { transform: translateX(-50%) translateY(0); opacity: 1; }
          50% { transform: translateX(-50%) translateY(8px); opacity: 0.6; }
        }
      `}</style>

      {/* ════════════════════════════════════════════════════
          SECTION 1 — HERO
      ════════════════════════════════════════════════════ */}
      <section style={{
        height: '100vh',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}>
        <StarfieldCanvas />

        {/* Center content */}
        <div style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          padding: '0 24px',
        }}>
          {/* Logo wordmark */}
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: 'easeOut' }}
            style={{
              fontFamily: '"Cormorant Garamond", serif',
              fontStyle: 'italic',
              fontWeight: 300,
              fontSize: 'clamp(64px, 10vw, 128px)',
              color: '#F0EDE6',
              letterSpacing: '0.06em',
              lineHeight: 1,
              margin: 0,
            }}
          >
            RehabAI
          </motion.h1>

          {/* Tagline */}
          <motion.p
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.5, ease: 'easeOut' }}
            style={{
              fontFamily: '"DM Sans", sans-serif',
              fontSize: '16px',
              color: 'rgba(240,237,230,0.55)',
              marginTop: '16px',
              letterSpacing: '0.03em',
            }}
          >
            AI-Powered Rehabilitation. Recovery Made Visible.
          </motion.p>

          {/* CTA buttons */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.85, ease: 'easeOut' }}
            style={{ display: 'flex', gap: '16px', marginTop: '40px', flexWrap: 'wrap', justifyContent: 'center' }}
          >
            <PillButton variant="gold" onClick={() => navigate('/auth')}>
              Get Started
            </PillButton>
            <PillButton variant="outline" onClick={() => {
              document.getElementById('section-problem')?.scrollIntoView({ behavior: 'smooth' })
            }}>
              Learn More
            </PillButton>
          </motion.div>
        </div>

        {/* Scroll chevron */}
        <ScrollChevron />
      </section>

      {/* ════════════════════════════════════════════════════
          SECTION 2 — THE PROBLEM
      ════════════════════════════════════════════════════ */}
      <section
        id="section-problem"
        ref={problemRef}
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px 24px',
          textAlign: 'center',
        }}
      >
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '40px',
        }}>
          <ProblemLine text="Rehabilitation is lonely." delay={0}    inView={problemInView} />
          <ProblemLine text="Recovery is invisible."   delay={0.25}  inView={problemInView} />
          <ProblemLine text="We changed that."         delay={0.5}   inView={problemInView} color="#C9A84C" />
        </div>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={problemInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.7, delay: 0.85, ease: 'easeOut' }}
          style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '15px',
            color: 'rgba(240,237,230,0.55)',
            maxWidth: '480px',
            lineHeight: 1.75,
            margin: 0,
          }}
        >
          Millions recover alone with no way for doctors to track progress in real time.
          RehabAI closes that gap.
        </motion.p>

        {/* Decorative divider */}
        <motion.div
          initial={{ scaleX: 0, opacity: 0 }}
          animate={problemInView ? { scaleX: 1, opacity: 1 } : {}}
          transition={{ duration: 1, delay: 1.1, ease: 'easeOut' }}
          style={{
            marginTop: '64px',
            height: '1px',
            width: '120px',
            background: 'linear-gradient(90deg, transparent, rgba(201,168,76,0.5), transparent)',
            transformOrigin: 'center',
          }}
        />
      </section>

      {/* ════════════════════════════════════════════════════
          SECTION 3 — TWO PATHS
      ════════════════════════════════════════════════════ */}
      <section
        ref={pathRef}
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px 24px 120px',
        }}
      >
        {/* Section heading */}
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={pathInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          style={{
            fontFamily: '"Cormorant Garamond", serif',
            fontStyle: 'italic',
            fontWeight: 300,
            fontSize: 'clamp(32px, 5vw, 48px)',
            color: '#F0EDE6',
            marginBottom: '52px',
            textAlign: 'center',
          }}
        >
          Choose Your Path
        </motion.h2>

        {/* Cards row */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={pathInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.7, delay: 0.2, ease: 'easeOut' }}
          style={{
            display: 'flex',
            flexDirection: 'row',
            gap: '24px',
            width: '100%',
            maxWidth: '800px',
            flexWrap: 'wrap',
          }}
        >
          {/* Doctor card */}
          <PathCard
            icon={<StethoscopeIcon />}
            title="I am a Doctor"
            description="Monitor all your patients from one clinical dashboard."
            buttonLabel="Doctor Login"
            buttonVariant="outline"
            onClick={() => navigate('/auth')}
          />

          {/* Patient card */}
          <PathCard
            icon={<PatientIcon />}
            title="I am a Patient"
            description="Begin your guided AI recovery session."
            buttonLabel="Patient Login"
            buttonVariant="gold"
            onClick={() => navigate('/auth')}
          />
        </motion.div>
      </section>

      {/* ════════════════════════════════════════════════════
          FIXED FOOTER
      ════════════════════════════════════════════════════ */}
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        textAlign: 'center',
        padding: '12px 24px',
        pointerEvents: 'none',
        zIndex: 50,
      }}>
        <span style={{
          fontFamily: '"DM Mono", monospace',
          fontSize: '10px',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: 'rgba(240,237,230,0.2)',
        }}>
          NAKSHATRA-01 · A.P. SHAH INSTITUTE OF TECHNOLOGY · 24HR HACKATHON
        </span>
      </div>

    </div>
  )
}

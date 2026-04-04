import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ResponsiveContainer, LineChart, Line } from 'recharts'
import { supabase } from '../../lib/supabase'
import { getExercises } from '../../lib/api'
import useAuthStore from '../../store/authStore'
import GlassCard from '../../components/ui/GlassCard'
import PillButton from '../../components/ui/PillButton'
import MonoChip from '../../components/ui/MonoChip'
import LoadingVoid from '../../components/ui/LoadingVoid'

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'GOOD MORNING,'
  if (h < 17) return 'GOOD AFTERNOON,'
  return 'GOOD EVENING,'
}

function fmtTodayLabel() {
  return new Date()
    .toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })
    .toUpperCase()
    .replace(/,/g, ' ·')
}

function emailPrefix(email = '') {
  return email.split('@')[0]
}

// ─────────────────────────────────────────────────────────────
// MINI SPARKLINE
// ─────────────────────────────────────────────────────────────
function Sparkline({ data, dataKey, stroke }) {
  if (!data?.length) {
    return (
      <div style={{
        height: '60px', display: 'flex', alignItems: 'center',
        fontFamily: '"DM Mono", monospace', fontSize: '10px',
        color: 'rgba(240,237,230,0.2)', letterSpacing: '0.08em',
      }}>
        NO DATA YET
      </div>
    )
  }
  return (
    <ResponsiveContainer width="100%" height={60}>
      <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <Line
          type="monotone"
          dataKey={dataKey}
          stroke={stroke}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={true}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ─────────────────────────────────────────────────────────────
// GAME PILL
// ─────────────────────────────────────────────────────────────
function GamePill({ gameName, bestLevel }) {
  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '4px 10px',
      borderRadius: '9999px',
      background: 'rgba(74,111,165,0.15)',
      border: '1px solid rgba(74,111,165,0.3)',
      fontFamily: '"DM Mono", monospace',
      fontSize: '10px',
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: '#4A6FA5',
      whiteSpace: 'nowrap',
    }}>
      {gameName?.replace(/-/g, ' ')} LVL {bestLevel}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// CARD ENTRANCE ANIMATION WRAPPER
// ─────────────────────────────────────────────────────────────
function FadeCard({ delay = 0, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  )
}

// ─────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────
export default function PatientHub() {
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()

  const [todaySession, setTodaySession] = useState(undefined)   // undefined = loading, null = none
  const [last7Physical, setLast7Physical] = useState([])
  const [last7Cognitive, setLast7Cognitive] = useState([])
  const [cogProgress, setCogProgress] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!user?.id) return

    const fetchAll = async () => {
      const today = todayISO()

      const [
        { data: todaySess },
        { data: physSessions },
        { data: cogSessions },
        { data: cogProg },
      ] = await Promise.all([
        supabase
          .from('rehab_sessions')
          .select('*')
          .eq('user_id', user.id)
          .eq('session_date', today)
          .maybeSingle(),                          // use maybeSingle to avoid 406 when no row
        supabase
          .from('rehab_sessions')
          .select('session_number, avg_accuracy_pct')
          .eq('user_id', user.id)
          .eq('completed', true)
          .order('session_number', { ascending: false })
          .limit(7),
        supabase
          .from('cognitive_game_sessions')
          .select('cog_score, played_at')
          .eq('user_id', user.id)
          .order('played_at', { ascending: false })
          .limit(7),
        supabase
          .from('cognitive_game_progress')
          .select('*')
          .eq('user_id', user.id),
      ])

      // Fire and forget exercises cache warm-up
      getExercises().catch(() => {})

      setTodaySession(todaySess ?? null)
      // Reverse for chronological sparkline direction
      setLast7Physical([...(physSessions ?? [])].reverse())
      setLast7Cognitive([...(cogSessions ?? [])].reverse())
      setCogProgress(cogProg ?? [])
      setLoading(false)
    }

    fetchAll()
  }, [user?.id])

  const handleLogout = async () => {
    await logout()
    navigate('/')
  }

  if (loading) return <LoadingVoid text="loading your recovery hub..." />

  // Derived
  const nextSessionNum = (last7Physical[last7Physical.length - 1]?.session_number ?? 0) + 1

  const physicalStatus = !todaySession
    ? 'none'
    : todaySession.completed
    ? 'completed'
    : 'in-progress'

  return (
    <div style={{
      background: '#08090F',
      minHeight: '100vh',
      padding: '32px',
      maxWidth: '1100px',
      margin: '0 auto',
      boxSizing: 'border-box',
      position: 'relative',
    }}>

      {/* ── HEADER ── */}
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '12px',
        }}>
          {/* Left */}
          <div>
            <p style={{
              fontFamily: '"DM Sans", sans-serif',
              fontSize: '13px',
              color: 'rgba(240,237,230,0.4)',
              margin: 0,
              letterSpacing: '0.05em',
            }}>
              {greeting()}
            </p>
            <h1 style={{
              fontFamily: '"Cormorant Garamond", serif',
              fontStyle: 'italic',
              fontWeight: 300,
              fontSize: 'clamp(36px, 5vw, 52px)',
              color: '#F0EDE6',
              margin: '4px 0 0',
              lineHeight: 1.1,
            }}>
              {emailPrefix(user?.email)}
            </h1>
          </div>

          {/* Right — date */}
          <span style={{
            fontFamily: '"DM Mono", monospace',
            fontSize: '11px',
            letterSpacing: '0.1em',
            color: 'rgba(240,237,230,0.35)',
            paddingTop: '6px',
          }}>
            {fmtTodayLabel()}
          </span>
        </div>

        {/* Status chips row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '14px', flexWrap: 'wrap' }}>
          <MonoChip text={`REHAB DAY ${user?.rehab_day ?? 0}`} color="blue" />
          <MonoChip text={`PAIN TOLERANCE ${(user?.pain_tolerance ?? 1).toFixed(1)}`} color="dim" />
        </div>
      </motion.div>

      {/* ── TWO MAIN CARDS ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '24px',
        marginTop: '36px',
      }}>

        {/* ── CARD 1: PHYSICAL RECOVERY ── */}
        <FadeCard delay={0.1}>
          <GlassCard goldHover>
            <div style={{ padding: '28px' }}>
              <h2 style={{
                fontFamily: '"Cormorant Garamond", serif',
                fontStyle: 'italic', fontWeight: 300,
                fontSize: '32px', color: '#F0EDE6', margin: 0, lineHeight: 1.1,
              }}>
                Physical Recovery
              </h2>
              <p style={{
                fontFamily: '"DM Sans", sans-serif',
                fontSize: '13px', color: 'rgba(240,237,230,0.5)',
                margin: '6px 0 18px', lineHeight: 1.5,
              }}>
                MediaPipe joint tracking · Real-time angle analysis
              </p>

              {/* Status + action */}
              {physicalStatus === 'completed' && (
                <>
                  <MonoChip text="COMPLETED TODAY" color="gold" />
                  <p style={{
                    fontFamily: '"DM Mono", monospace',
                    fontSize: '12px', color: 'rgba(240,237,230,0.4)',
                    letterSpacing: '0.08em', textTransform: 'uppercase',
                    margin: '10px 0 16px',
                  }}>
                    {todaySession.total_reps ?? 0} REPS · {(todaySession.avg_accuracy_pct ?? 0).toFixed(0)}% ACCURACY
                  </p>
                  <PillButton variant="outline" disabled>
                    SESSION DONE ✓
                  </PillButton>
                </>
              )}

              {physicalStatus === 'in-progress' && (
                <>
                  <MonoChip text="IN PROGRESS" color="blue" />
                  <div style={{ marginTop: '16px' }}>
                    <PillButton variant="gold" onClick={() => navigate('/patient/session/physical')}>
                      Resume Session
                    </PillButton>
                  </div>
                </>
              )}

              {physicalStatus === 'none' && (
                <>
                  <MonoChip text="PENDING" color="dim" />
                  <div style={{ marginTop: '16px' }}>
                    <PillButton variant="gold" onClick={() => navigate('/patient/session/physical')}>
                      Begin Session
                    </PillButton>
                  </div>
                </>
              )}

              {/* Divider + session label */}
              <div style={{ height: '1px', background: 'rgba(255,255,255,0.07)', margin: '20px 0 14px' }} />
              <span style={{
                fontFamily: '"DM Mono", monospace',
                fontSize: '10px', letterSpacing: '0.1em',
                color: 'rgba(240,237,230,0.3)', textTransform: 'uppercase',
              }}>
                SESSION #{nextSessionNum} TODAY
              </span>
            </div>
          </GlassCard>
        </FadeCard>

        {/* ── CARD 2: COGNITIVE TRAINING ── */}
        <FadeCard delay={0.18}>
          <GlassCard goldHover>
            <div style={{ padding: '28px' }}>
              <h2 style={{
                fontFamily: '"Cormorant Garamond", serif',
                fontStyle: 'italic', fontWeight: 300,
                fontSize: '32px', color: '#F0EDE6', margin: 0, lineHeight: 1.1,
              }}>
                Cognitive Training
              </h2>
              <p style={{
                fontFamily: '"DM Sans", sans-serif',
                fontSize: '13px', color: 'rgba(240,237,230,0.5)',
                margin: '6px 0 0', lineHeight: 1.5,
              }}>
                Memory, pattern, and recall games
              </p>

              {/* Game pills */}
              {cogProgress.length > 0 && (
                <div style={{
                  display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '18px',
                }}>
                  {cogProgress.slice(0, 3).map(g => (
                    <GamePill key={g.id} gameName={g.game_name} bestLevel={g.best_level} />
                  ))}
                </div>
              )}

              {/* Cog score */}
              {(user?.overall_cog_score ?? 0) > 0 && (
                <p style={{
                  fontFamily: '"DM Mono", monospace',
                  fontSize: '12px', color: 'rgba(240,237,230,0.4)',
                  letterSpacing: '0.08em', textTransform: 'uppercase',
                  margin: '12px 0 0',
                }}>
                  OVERALL COG SCORE: {(user.overall_cog_score).toFixed(1)}
                </p>
              )}

              <div style={{ marginTop: '20px' }}>
                <PillButton variant="gold" onClick={() => navigate('/patient/session/cognitive')}>
                  Train Your Mind
                </PillButton>
              </div>
            </div>
          </GlassCard>
        </FadeCard>
      </div>

      {/* ── MINI PROGRESS SECTION ── */}
      <FadeCard delay={0.28}>
        <div style={{ marginTop: '44px' }}>

          {/* Section header */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: '18px',
          }}>
            <span style={{
              fontFamily: '"DM Mono", monospace',
              fontSize: '11px', letterSpacing: '0.12em',
              textTransform: 'uppercase', color: 'rgba(240,237,230,0.4)',
            }}>
              Recent Progress
            </span>
            <button
              onClick={() => navigate('/patient/progress')}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontFamily: '"DM Mono", monospace', fontSize: '11px',
                letterSpacing: '0.1em', textTransform: 'uppercase',
                color: '#C9A84C', padding: 0,
                transition: 'opacity 200ms',
              }}
              onMouseEnter={e => e.currentTarget.style.opacity = '0.7'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              VIEW FULL →
            </button>
          </div>

          {/* Sparkline grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '16px',
          }}>

            {/* Physical sparkline */}
            <GlassCard>
              <div style={{ padding: '16px' }}>
                <span style={{
                  fontFamily: '"DM Mono", monospace',
                  fontSize: '10px', letterSpacing: '0.1em',
                  textTransform: 'uppercase', color: 'rgba(240,237,230,0.4)',
                  display: 'block', marginBottom: '8px',
                }}>
                  Physical Accuracy
                </span>
                <Sparkline
                  data={last7Physical}
                  dataKey="avg_accuracy_pct"
                  stroke="#4A6FA5"
                />
              </div>
            </GlassCard>

            {/* Cognitive sparkline */}
            <GlassCard>
              <div style={{ padding: '16px' }}>
                <span style={{
                  fontFamily: '"DM Mono", monospace',
                  fontSize: '10px', letterSpacing: '0.1em',
                  textTransform: 'uppercase', color: 'rgba(240,237,230,0.4)',
                  display: 'block', marginBottom: '8px',
                }}>
                  Cognitive Score
                </span>
                <Sparkline
                  data={last7Cognitive}
                  dataKey="cog_score"
                  stroke="#C9A84C"
                />
              </div>
            </GlassCard>
          </div>
        </div>
      </FadeCard>

      {/* ── SIGN OUT ── */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end',
        marginTop: '48px',
      }}>
        <button
          onClick={handleLogout}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontFamily: '"DM Mono", monospace',
            fontSize: '10px', letterSpacing: '0.12em',
            textTransform: 'uppercase', color: 'rgba(240,237,230,0.25)',
            padding: '4px 0',
            transition: 'color 200ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = '#C47474'}
          onMouseLeave={e => e.currentTarget.style.color = 'rgba(240,237,230,0.25)'}
        >
          SIGN OUT
        </button>
      </div>

    </div>
  )
}

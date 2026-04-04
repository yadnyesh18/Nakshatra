import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { supabase } from '../../lib/supabase'
import useAuthStore from '../../store/authStore'
import RecoveryGraphs from '../../components/RecoveryGraphs'
import GlassCard from '../../components/ui/GlassCard'
import MonoChip from '../../components/ui/MonoChip'
import LoadingVoid from '../../components/ui/LoadingVoid'

// ─────────────────────────────────────────────────────────────
// GAME CARD
// ─────────────────────────────────────────────────────────────
function GameCard({ game, index }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.07, ease: 'easeOut' }}
    >
      <GlassCard>
        <div style={{ padding: '18px 20px' }}>
          <div style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '14px', fontWeight: 600,
            color: '#F0EDE6',
            textTransform: 'capitalize',
            marginBottom: '10px',
          }}>
            {game.game_name?.replace(/-/g, ' ')}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
            <MonoChip text={`SESSIONS: ${game.sessions_played ?? 0}`} color="white" />
            <MonoChip text={`BEST LVL: ${game.best_level ?? 0}`} color="blue" />
            <MonoChip text={`AVG: ${(game.avg_cog_score ?? 0).toFixed(0)}%`} color="gold" />
          </div>

          <div style={{
            fontFamily: '"DM Mono", monospace',
            fontSize: '10px', letterSpacing: '0.08em',
            color: 'rgba(240,237,230,0.3)',
            textTransform: 'uppercase',
          }}>
            TREND: {(game.recent_trend ?? 'not enough data').toUpperCase()}
          </div>
        </div>
      </GlassCard>
    </motion.div>
  )
}

// ─────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────
export default function PatientProgressView() {
  const navigate = useNavigate()
  const { user } = useAuthStore()

  const [cogProgress, setCogProgress] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!user?.id) return
    supabase
      .from('cognitive_game_progress')
      .select('*')
      .eq('user_id', user.id)
      .then(({ data }) => {
        setCogProgress(data ?? [])
        setLoading(false)
      })
  }, [user?.id])

  if (loading) return <LoadingVoid text="loading recovery journey..." />

  return (
    <div style={{
      background: '#08090F',
      minHeight: '100vh',
      padding: '40px',
      boxSizing: 'border-box',
      maxWidth: '1000px',
      margin: '0 auto',
    }}>

      {/* ── Back link ── */}
      <button
        onClick={() => navigate('/patient/hub')}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: '"DM Mono", monospace', fontSize: '11px',
          letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'rgba(201,168,76,0.7)',
          padding: '0 0 4px 0',
          transition: 'color 200ms',
        }}
        onMouseEnter={e => e.currentTarget.style.color = '#C9A84C'}
        onMouseLeave={e => e.currentTarget.style.color = 'rgba(201,168,76,0.7)'}
      >
        ← HUB
      </button>

      {/* ── Heading ── */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      >
        <h1 style={{
          fontFamily: '"Cormorant Garamond", serif',
          fontStyle: 'italic', fontWeight: 300,
          fontSize: 'clamp(40px, 6vw, 56px)',
          color: '#F0EDE6',
          margin: '24px 0 0',
          lineHeight: 1.1,
        }}>
          Your Recovery Journey
        </h1>

        <p style={{
          fontFamily: '"DM Mono", monospace',
          fontSize: '11px', letterSpacing: '0.1em',
          color: 'rgba(240,237,230,0.3)',
          textTransform: 'uppercase',
          margin: '10px 0 32px',
        }}>
          {user?.email} · REHAB DAY {user?.rehab_day ?? 0}
        </p>
      </motion.div>

      {/* ── Recovery Graphs ── */}
      <RecoveryGraphs userId={user?.id} isDoctor={false} />

      {/* ── Game Breakdown ── */}
      <div style={{ marginTop: '40px' }}>
        <div style={{
          fontFamily: '"DM Mono", monospace',
          fontSize: '11px', letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'rgba(240,237,230,0.4)',
          marginBottom: '18px',
        }}>
          Game Breakdown
        </div>

        {cogProgress.length === 0 ? (
          <div style={{
            fontFamily: '"DM Mono", monospace', fontSize: '11px',
            color: 'rgba(240,237,230,0.25)', letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}>
            NO GAME DATA YET — COMPLETE A COGNITIVE SESSION FIRST
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: '16px',
          }}>
            {cogProgress.map((game, i) => (
              <GameCard key={game.id} game={game} index={i} />
            ))}
          </div>
        )}
      </div>

    </div>
  )
}

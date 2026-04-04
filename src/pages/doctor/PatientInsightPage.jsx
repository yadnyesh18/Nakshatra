import { useEffect, useState, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { supabase } from '../../lib/supabase'
import RecoveryGraphs from '../../components/RecoveryGraphs'
import GlassCard from '../../components/ui/GlassCard'
import MonoChip from '../../components/ui/MonoChip'
import LoadingVoid from '../../components/ui/LoadingVoid'

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function fmtDateLong(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()
}

function fmtDateShort(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase()
}

function emailFirstLetter(email = '') {
  return (email[0] || '?').toUpperCase()
}

// ─────────────────────────────────────────────────────────────
// LIVE DOT
// ─────────────────────────────────────────────────────────────
function LiveDot() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '24px' }}>
      <style>{`@keyframes liveDot { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
      <div style={{
        width: '7px', height: '7px', borderRadius: '50%',
        background: '#4CAF82',
        animation: 'liveDot 1.8s ease-in-out infinite',
      }} />
      <span style={{
        fontFamily: '"DM Mono", monospace', fontSize: '10px',
        letterSpacing: '0.12em', color: 'rgba(240,237,230,0.5)',
      }}>
        LIVE DATA
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// SIDEBAR INFO ROW
// ─────────────────────────────────────────────────────────────
function InfoRow({ label, value }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{
        fontFamily: '"DM Mono", monospace', fontSize: '10px',
        letterSpacing: '0.1em', textTransform: 'uppercase',
        color: 'rgba(240,237,230,0.4)',
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: '"DM Sans", sans-serif', fontSize: '14px',
        color: '#F0EDE6',
      }}>
        {value}
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// AXIS TICK STYLE
// ─────────────────────────────────────────────────────────────
const TICK_STYLE = {
  fontFamily: '"DM Mono", monospace',
  fontSize: 10,
  fill: 'rgba(240,237,230,0.4)',
  letterSpacing: '0.05em',
}

// ─────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────
export default function PatientInsightPage() {
  const { userId } = useParams()
  const navigate = useNavigate()

  const [patient, setPatient] = useState(null)
  const [cogProgress, setCogProgress] = useState([])
  const [loading, setLoading] = useState(true)

  const channelRef = useRef(null)

  const fetchAll = async () => {
    const [{ data: patientData }, { data: cogProgressData }] = await Promise.all([
      supabase.from('users').select('*').eq('id', userId).single(),
      supabase.from('cognitive_game_progress').select('*').eq('user_id', userId),
    ])
    setPatient(patientData)
    setCogProgress(cogProgressData ?? [])
    setLoading(false)
  }

  useEffect(() => {
    fetchAll()
    // RecoveryGraphs handles its own realtime subscriptions
    return () => { if (channelRef.current) supabase.removeChannel(channelRef.current) }
  }, [userId])

  if (loading) return <LoadingVoid text="loading patient data..." />
  if (!patient) return (
    <div style={{ color: '#C47474', fontFamily: '"DM Mono"', padding: 40 }}>
      PATIENT NOT FOUND
    </div>
  )


  return (
    <div style={{
      background: '#08090F',
      minHeight: '100vh',
      padding: '32px',
      boxSizing: 'border-box',
      display: 'flex',
      gap: '32px',
      flexWrap: 'wrap',
      alignItems: 'flex-start',
    }}>

      {/* ════════════════════════════════
          SIDEBAR
      ════════════════════════════════ */}
      <aside style={{
        width: '280px',
        flexShrink: 0,
        position: 'sticky',
        top: '32px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Avatar */}
        <div style={{
          width: '72px', height: '72px', borderRadius: '50%',
          background: 'rgba(255,255,255,0.03)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255,255,255,0.1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: '14px',
        }}>
          <span style={{
            fontFamily: '"Cormorant Garamond", serif',
            fontStyle: 'italic',
            fontSize: '32px',
            fontWeight: 300,
            color: '#C9A84C',
            lineHeight: 1,
          }}>
            {emailFirstLetter(patient.email)}
          </span>
        </div>

        {/* Email */}
        <span style={{
          fontFamily: '"DM Sans", sans-serif',
          fontSize: '15px',
          fontWeight: 600,
          color: '#F0EDE6',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          maxWidth: '100%',
        }}>
          {patient.email}
        </span>

        {/* Info stack */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '20px' }}>
          <InfoRow label="Rehab Day"          value={patient.rehab_day ?? '—'} />
          <InfoRow label="Start Date"         value={fmtDateLong(patient.rehab_start_date)} />
          <InfoRow label="Pain Tolerance"     value={(patient.pain_tolerance ?? 1).toFixed(2)} />
          <InfoRow label="Total Cog Sessions" value={patient.total_cog_sessions ?? 0} />
          <InfoRow label="Overall Cog Score"  value={(patient.overall_cog_score ?? 0).toFixed(1)} />
        </div>

        {/* Divider */}
        <div style={{ height: '1px', background: 'rgba(255,255,255,0.07)', margin: '22px 0' }} />

        {/* Cognitive games */}
        <div style={{
          fontFamily: '"DM Mono", monospace',
          fontSize: '10px',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'rgba(240,237,230,0.4)',
          marginBottom: '12px',
        }}>
          Cognitive Games
        </div>

        {cogProgress.length === 0 && (
          <span style={{
            fontFamily: '"DM Mono", monospace', fontSize: '10px',
            color: 'rgba(240,237,230,0.25)', letterSpacing: '0.08em',
          }}>
            NO GAME DATA YET
          </span>
        )}

        {cogProgress.map(g => (
          <motion.div
            key={g.id}
            style={{
              background: 'rgba(255,255,255,0.03)',
              backdropFilter: 'blur(20px)',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: '10px',
              padding: '12px 14px',
              marginBottom: '8px',
            }}
            whileHover={{ borderColor: 'rgba(201,168,76,0.3)' }}
          >
            <div style={{
              fontFamily: '"DM Sans", sans-serif',
              fontSize: '13px',
              fontWeight: 600,
              color: '#F0EDE6',
              textTransform: 'capitalize',
              marginBottom: '8px',
            }}>
              {g.game_name?.replace(/-/g, ' ')}
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
              <MonoChip text={`LVL ${g.best_level}`} color="blue" />
              <MonoChip text={`AVG ${(g.avg_cog_score ?? 0).toFixed(0)}%`} color="gold" />
            </div>
            <div style={{
              fontFamily: '"DM Mono", monospace', fontSize: '10px',
              color: 'rgba(240,237,230,0.3)', letterSpacing: '0.07em',
              textTransform: 'uppercase',
            }}>
              {g.sessions_played} SESSIONS · {(g.recent_trend ?? '').toUpperCase()}
            </div>
          </motion.div>
        ))}
      </aside>

      {/* ════════════════════════════════
          MAIN CONTENT
      ════════════════════════════════ */}
      <main style={{ flex: 1, minWidth: 0 }}>

        {/* Back button */}
        <button
          onClick={() => navigate('/doctor/dashboard')}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontFamily: '"DM Mono", monospace', fontSize: '11px',
            letterSpacing: '0.12em', textTransform: 'uppercase',
            color: 'rgba(201,168,76,0.7)',
            padding: '0 0 24px 0',
            display: 'flex', alignItems: 'center', gap: '6px',
            transition: 'color 200ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = '#C9A84C'}
          onMouseLeave={e => e.currentTarget.style.color = 'rgba(201,168,76,0.7)'}
        >
          ← ROSTER
        </button>

        <LiveDot />

        {/* Charts delegated to shared RecoveryGraphs — handles its own fetch + realtime */}
        <RecoveryGraphs userId={userId} isDoctor={true} />

      </main>
    </div>
  )
}

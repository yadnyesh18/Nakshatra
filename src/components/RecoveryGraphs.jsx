import { useEffect, useState, useRef } from 'react'
import { motion } from 'framer-motion'
import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import { supabase } from '../lib/supabase'
import GlassCard from './ui/GlassCard'
import MonoChip from './ui/MonoChip'

// ─────────────────────────────────────────────────────────────
// TREND CALCULATOR
// ─────────────────────────────────────────────────────────────
function calcTrend(values = []) {
  if (values.length < 2) return { label: '→ STABLE', color: 'blue' }
  const last5 = values.slice(-5)
  const slope = (last5[last5.length - 1] - last5[0]) / last5.length
  if (slope > 2)  return { label: '↑ IMPROVING',    color: 'gold' }
  if (slope > -2) return { label: '→ STABLE',        color: 'blue' }
  return              { label: '↓ NEEDS REVIEW',     color: 'red'  }
}

// ─────────────────────────────────────────────────────────────
// AXIS TICK STYLE (shared)
// ─────────────────────────────────────────────────────────────
const TICK = {
  fontFamily: '"DM Mono", monospace',
  fontSize: 10,
  fill: 'rgba(240,237,230,0.4)',
}

// ─────────────────────────────────────────────────────────────
// PHYSICAL TOOLTIP
// ─────────────────────────────────────────────────────────────
function PhysTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload ?? {}
  return (
    <div style={{
      background: '#0d0e17',
      border: '1px solid rgba(201,168,76,0.25)',
      borderRadius: '8px',
      padding: '12px 14px',
    }}>
      <div style={{ fontFamily: '"DM Mono"', fontSize: '10px', color: 'rgba(240,237,230,0.5)', marginBottom: '4px' }}>
        SESSION {d.session_number}
      </div>
      <div style={{ fontFamily: '"DM Mono"', fontSize: '14px', color: '#C9A84C' }}>
        {d.avg_accuracy_pct != null ? d.avg_accuracy_pct.toFixed(1) : '—'}% ACCURACY
      </div>
      <div style={{ fontFamily: '"DM Mono"', fontSize: '10px', color: 'rgba(240,237,230,0.4)', marginTop: '4px' }}>
        {d.total_reps ?? '—'} REPS
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// COGNITIVE TOOLTIP
// ─────────────────────────────────────────────────────────────
function CogTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload ?? {}
  const dateLabel = d.played_at
    ? new Date(d.played_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase()
    : '—'
  return (
    <div style={{
      background: '#0d0e17',
      border: '1px solid rgba(201,168,76,0.25)',
      borderRadius: '8px',
      padding: '12px 14px',
    }}>
      <div style={{ fontFamily: '"DM Mono"', fontSize: '10px', color: 'rgba(240,237,230,0.5)', marginBottom: '4px' }}>
        {dateLabel}
      </div>
      <div style={{ fontFamily: '"DM Mono"', fontSize: '14px', color: '#C9A84C' }}>
        {d.cog_score != null ? d.cog_score.toFixed(1) : '—'} SCORE
      </div>
      {d.game_name && (
        <div style={{ fontFamily: '"DM Mono"', fontSize: '10px', color: 'rgba(240,237,230,0.4)', marginTop: '4px', textTransform: 'uppercase' }}>
          {d.game_name?.replace(/-/g, ' ')} · LVL {d.level_reached ?? '—'}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// EMPTY CHART STATE
// ─────────────────────────────────────────────────────────────
function EmptyChart({ label }) {
  return (
    <div style={{
      height: '260px',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: '"DM Mono", monospace', fontSize: '11px',
      color: 'rgba(240,237,230,0.2)', letterSpacing: '0.1em', textTransform: 'uppercase',
    }}>
      {label}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// CHART HEADER
// ─────────────────────────────────────────────────────────────
function ChartHeader({ title, trend, baselineChip }) {
  return (
    <div style={{ marginBottom: baselineChip ? '10px' : '20px' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', flexWrap: 'wrap', gap: '10px',
      }}>
        <h2 style={{
          fontFamily: '"Cormorant Garamond", serif',
          fontStyle: 'italic', fontWeight: 300,
          fontSize: '28px', color: '#F0EDE6', margin: 0,
        }}>
          {title}
        </h2>
        {trend && <MonoChip text={trend.label} color={trend.color} />}
      </div>
      {baselineChip && (
        <div style={{ marginTop: '10px', marginBottom: '16px' }}>
          {baselineChip}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────
/**
 * RecoveryGraphs — self-contained chart component.
 * Props:
 *   userId   (string) — whose data to display
 *   isDoctor (bool)   — shows baseline chip when true
 */
export default function RecoveryGraphs({ userId, isDoctor = false }) {
  const [rehabSessions, setRehabSessions] = useState([])
  const [cogSessions, setCogSessions]     = useState([])
  const [loading, setLoading]             = useState(true)
  const channelsRef = useRef([])

  const fetchData = async () => {
    const [{ data: rs }, { data: cs }] = await Promise.all([
      supabase
        .from('rehab_sessions')
        .select('session_number, avg_accuracy_pct, total_reps, rehab_day, session_date')
        .eq('user_id', userId)
        .eq('completed', true)
        .order('session_number', { ascending: true }),
      supabase
        .from('cognitive_game_sessions')
        .select('cog_score, played_at, game_name, level_reached')
        .eq('user_id', userId)
        .order('played_at', { ascending: true }),
    ])
    setRehabSessions(rs ?? [])
    setCogSessions(cs ?? [])
    setLoading(false)
  }

  useEffect(() => {
    if (!userId) return
    fetchData()

    // Realtime subscription — both tables
    const physCh = supabase
      .channel(`rg-phys-${userId}`)
      .on('postgres_changes', {
        event: '*', schema: 'public', table: 'rehab_sessions',
        filter: `user_id=eq.${userId}`,
      }, fetchData)
      .subscribe()

    const cogCh = supabase
      .channel(`rg-cog-${userId}`)
      .on('postgres_changes', {
        event: '*', schema: 'public', table: 'cognitive_game_sessions',
        filter: `user_id=eq.${userId}`,
      }, fetchData)
      .subscribe()

    channelsRef.current = [physCh, cogCh]
    return () => {
      channelsRef.current.forEach(ch => supabase.removeChannel(ch))
    }
  }, [userId])

  // ── Derived ───────────────────────────────────────────────
  const physAccuracies = rehabSessions.map(s => s.avg_accuracy_pct).filter(v => v != null)
  const cogScores      = cogSessions.map(s => s.cog_score).filter(v => v != null)
  const physTrend      = calcTrend(physAccuracies)
  const cogTrend       = calcTrend(cogScores)

  const baselineAccuracy = rehabSessions[0]?.avg_accuracy_pct

  // Format cog date for XAxis tick
  const fmtDate = (val) => {
    if (!val) return ''
    try {
      return new Date(val).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase()
    } catch { return '' }
  }

  if (loading) {
    return (
      <div style={{ padding: '40px 0', textAlign: 'center' }}>
        <span style={{
          fontFamily: '"DM Mono", monospace', fontSize: '10px',
          color: 'rgba(240,237,230,0.3)', letterSpacing: '0.12em',
        }}>
          LOADING GRAPHS...
        </span>
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: 'easeOut' }}
    >
      {/* ── PHYSICAL RECOVERY ── */}
      <GlassCard>
        <div style={{ padding: '28px' }}>
          <ChartHeader
            title="Physical Recovery"
            trend={physTrend}
            baselineChip={
              isDoctor && baselineAccuracy != null
                ? <MonoChip text={`BASELINE S1 · ${baselineAccuracy.toFixed(0)}%`} color="blue" />
                : null
            }
          />

          {rehabSessions.length === 0 ? (
            <EmptyChart label="No physical session data yet" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={rehabSessions} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                <defs>
                  <linearGradient id="physGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#4A6FA5" stopOpacity="0.2" />
                    <stop offset="95%" stopColor="#4A6FA5" stopOpacity="0"   />
                  </linearGradient>
                </defs>

                <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="session_number"
                  tickFormatter={n => `S${n}`}
                  tick={TICK}
                  axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tickFormatter={n => `${n}%`}
                  tick={TICK}
                  axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
                  tickLine={false}
                />
                <Tooltip content={<PhysTooltip />} />
                <ReferenceLine
                  y={50}
                  stroke="rgba(255,255,255,0.08)"
                  strokeDasharray="4 4"
                  label={{ value: '50%', fill: 'rgba(255,255,255,0.2)', fontFamily: 'DM Mono', fontSize: 9 }}
                />
                <Area
                  type="monotone"
                  dataKey="avg_accuracy_pct"
                  fill="url(#physGrad)"
                  stroke="none"
                />
                <Line
                  type="monotone"
                  dataKey="avg_accuracy_pct"
                  stroke="#4A6FA5"
                  strokeWidth={2}
                  dot={{ fill: '#C9A84C', r: 4, strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: '#C9A84C', strokeWidth: 0 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </GlassCard>

      {/* ── COGNITIVE RECOVERY ── */}
      <div style={{ marginTop: '24px' }}>
        <GlassCard>
          <div style={{ padding: '28px' }}>
            <ChartHeader title="Cognitive Recovery" trend={cogTrend} />

            {cogSessions.length === 0 ? (
              <EmptyChart label="No cognitive game data yet" />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={cogSessions} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                  <defs>
                    <linearGradient id="cogGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#C9A84C" stopOpacity="0.2" />
                      <stop offset="95%" stopColor="#C9A84C" stopOpacity="0"   />
                    </linearGradient>
                  </defs>

                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="played_at"
                    tickFormatter={fmtDate}
                    tick={TICK}
                    axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    domain={[0, 100]}
                    tickFormatter={n => `${n}%`}
                    tick={TICK}
                    axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
                    tickLine={false}
                  />
                  <Tooltip content={<CogTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="cog_score"
                    fill="url(#cogGrad)"
                    stroke="none"
                  />
                  <Line
                    type="monotone"
                    dataKey="cog_score"
                    stroke="#C9A84C"
                    strokeWidth={2}
                    dot={{ fill: '#C9A84C', r: 3, strokeWidth: 0 }}
                    activeDot={{ r: 5, fill: '#F0EDE6', strokeWidth: 0 }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlassCard>
      </div>
    </motion.div>
  )
}

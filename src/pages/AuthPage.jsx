import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { supabase } from '../lib/supabase'
import useAuthStore from '../store/authStore'
import GlassCard from '../components/ui/GlassCard'
import PillButton from '../components/ui/PillButton'
import MonoChip from '../components/ui/MonoChip'

// ── Eye Toggle SVG Icons ─────────────────────────────────────
function EyeOpenIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function EyeClosedIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}

// ── Styled Input ─────────────────────────────────────────────
function AuthInput({ label, type, value, onChange, autoComplete, rightElement }) {
  const [focused, setFocused] = useState(false)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <label style={{
        fontFamily: '"DM Mono", monospace',
        fontSize: '11px',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'rgba(240,237,230,0.5)',
      }}>
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          type={type}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            width: '100%',
            background: 'rgba(255,255,255,0.05)',
            border: focused
              ? '1px solid #C9A84C'
              : '1px solid rgba(255,255,255,0.1)',
            boxShadow: focused
              ? '0 0 0 2px rgba(201,168,76,0.12)'
              : 'none',
            borderRadius: '8px',
            padding: rightElement ? '14px 48px 14px 16px' : '14px 16px',
            color: '#F0EDE6',
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '15px',
            outline: 'none',
            transition: 'border-color 200ms ease, box-shadow 200ms ease',
            boxSizing: 'border-box',
          }}
        />
        {rightElement && (
          <div style={{
            position: 'absolute',
            right: '14px',
            top: '50%',
            transform: 'translateY(-50%)',
            display: 'flex',
            alignItems: 'center',
          }}>
            {rightElement}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main AuthPage ─────────────────────────────────────────────
export default function AuthPage() {
  const navigate = useNavigate()
  const { login } = useAuthStore()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!email || !password) {
      setErrorMsg('Please enter your email and password.')
      return
    }

    setIsLoading(true)
    setErrorMsg('')

    try {
      // Sign in via Supabase Auth
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })

      if (error) {
        setErrorMsg('Invalid credentials. Contact your administrator.')
        setIsLoading(false)
        return
      }

      // Fetch full profile from public.users
      const { data: userData, error: profileError } = await supabase
        .from('users')
        .select('*')
        .eq('id', data.user.id)
        .single()

      if (profileError || !userData) {
        setErrorMsg('Profile not found. Contact your administrator.')
        setIsLoading(false)
        return
      }

      // Sync to Zustand store
      await login(email, password)

      // Role-based routing
      if (userData.role === 'doctor') {
        navigate('/doctor/dashboard')
      } else {
        navigate('/patient/hub')
      }
    } catch (err) {
      setErrorMsg('An unexpected error occurred. Please try again.')
      setIsLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#08090F',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      padding: '24px',
    }}>

      {/* ── Back link ── */}
      <button
        onClick={() => navigate('/')}
        style={{
          position: 'absolute',
          top: '28px',
          left: '28px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontFamily: '"DM Mono", monospace',
          fontSize: '11px',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'rgba(201,168,76,0.7)',
          padding: '4px 0',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          transition: 'color 200ms ease',
        }}
        onMouseEnter={e => e.currentTarget.style.color = '#C9A84C'}
        onMouseLeave={e => e.currentTarget.style.color = 'rgba(201,168,76,0.7)'}
      >
        ← BACK
      </button>

      {/* ── Animated Card ── */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        style={{ width: '100%', maxWidth: '440px' }}
      >
        <GlassCard>
          <form
            onSubmit={handleSubmit}
            style={{ padding: '48px' }}
            noValidate
          >

            {/* ── Header ── */}
            <div style={{ textAlign: 'center', marginBottom: '0' }}>
              <h1 style={{
                fontFamily: '"Cormorant Garamond", serif',
                fontStyle: 'italic',
                fontWeight: 300,
                fontSize: '52px',
                color: '#F0EDE6',
                lineHeight: 1.1,
                margin: 0,
              }}>
                RehabAI
              </h1>
              <p style={{
                fontFamily: '"DM Mono", monospace',
                fontSize: '11px',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: 'rgba(240,237,230,0.3)',
                marginTop: '10px',
                marginBottom: 0,
              }}>
                NAKSHATRA-01 · SECURE ACCESS
              </p>
            </div>

            {/* ── Divider ── */}
            <div style={{
              height: '1px',
              background: 'rgba(255,255,255,0.07)',
              margin: '28px 0',
            }} />

            {/* ── Form Fields ── */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

              {/* Email */}
              <AuthInput
                label="Email Address"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
              />

              {/* Password */}
              <AuthInput
                label="Password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                rightElement={
                  <button
                    type="button"
                    onClick={() => setShowPassword(v => !v)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'rgba(240,237,230,0.4)',
                      padding: 0,
                      display: 'flex',
                      alignItems: 'center',
                      transition: 'color 200ms ease',
                    }}
                    onMouseEnter={e => e.currentTarget.style.color = '#C9A84C'}
                    onMouseLeave={e => e.currentTarget.style.color = 'rgba(240,237,230,0.4)'}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeClosedIcon /> : <EyeOpenIcon />}
                  </button>
                }
              />

              {/* Error chip */}
              <AnimatePresence>
                {errorMsg && (
                  <motion.div
                    key="error"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2 }}
                    style={{ display: 'flex', alignItems: 'center' }}
                  >
                    <MonoChip text={errorMsg} color="red" />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Submit */}
              <div style={{ marginTop: '8px' }}>
                <PillButton
                  variant="gold"
                  loading={isLoading}
                  onClick={handleSubmit}
                  fullWidth
                >
                  Access Portal
                </PillButton>
              </div>

            </div>
          </form>
        </GlassCard>

        {/* ── Footer text ── */}
        <p style={{
          fontFamily: '"DM Sans", sans-serif',
          fontSize: '12px',
          color: 'rgba(240,237,230,0.3)',
          textAlign: 'center',
          marginTop: '20px',
        }}>
          Access is provided by your healthcare administrator.
        </p>
      </motion.div>
    </div>
  )
}

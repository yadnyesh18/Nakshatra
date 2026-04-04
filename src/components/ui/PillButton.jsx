import { motion } from 'framer-motion'

// Spinning loader SVG — gold, 16px
function SpinnerIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <circle
        cx="8"
        cy="8"
        r="6"
        stroke="rgba(201,168,76,0.3)"
        strokeWidth="2"
      />
      <path
        d="M8 2 A6 6 0 0 1 14 8"
        stroke="#C9A84C"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

const VARIANT_STYLES = {
  gold: {
    border: '1px solid #C9A84C',
    color: '#C9A84C',
    background: 'transparent',
  },
  outline: {
    border: '1px solid rgba(240,237,230,0.25)',
    color: '#F0EDE6',
    background: 'transparent',
  },
  danger: {
    border: '1px solid #C47474',
    color: '#C47474',
    background: 'transparent',
  },
}

const HOVER_STYLES = {
  gold: { background: '#C9A84C', color: '#08090F' },
  outline: { background: 'rgba(240,237,230,0.08)', color: '#F0EDE6' },
  danger: { background: '#C47474', color: '#08090F' },
}

/**
 * PillButton — Nakshatra pill-shaped action button.
 *
 * Props:
 *   children  — button label content
 *   onClick   — click handler
 *   variant   — 'gold' | 'outline' | 'danger'  (default: 'gold')
 *   disabled  — bool
 *   loading   — bool: replaces children with spinner
 *   className — extra classes
 */
export default function PillButton({
  children,
  onClick,
  variant = 'gold',
  disabled = false,
  loading = false,
  fullWidth = false,
  style = {},
  className = '',
}) {
  const baseStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    borderRadius: '9999px',
    padding: '0.5rem 1.5rem',
    fontFamily: '"DM Mono", monospace',
    fontSize: '0.75rem',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    outline: 'none',
    transition: 'all 200ms ease',
    opacity: disabled ? 0.45 : 1,
    width: fullWidth ? '100%' : undefined,
    ...VARIANT_STYLES[variant],
    ...style,
  }

  return (
    <motion.button
      style={baseStyle}
      whileHover={!disabled && !loading ? HOVER_STYLES[variant] : undefined}
      whileTap={!disabled && !loading ? { scale: 0.97 } : undefined}
      initial={{ scale: 1 }}
      onClick={disabled || loading ? undefined : onClick}
      disabled={disabled || loading}
      className={className}
      aria-disabled={disabled || loading}
    >
      {loading ? <SpinnerIcon /> : children}
    </motion.button>
  )
}

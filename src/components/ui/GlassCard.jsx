import { motion } from 'framer-motion'

/**
 * GlassCard — Nakshatra glassmorphic container.
 *
 * Props:
 *   children    — React children
 *   className   — extra Tailwind / CSS classes
 *   onClick     — click handler
 *   goldHover   — bool: adds gold border + glow on hover via Framer Motion
 */
export default function GlassCard({ children, className = '', onClick, goldHover = false }) {
  const baseStyle = {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.07)',
    borderRadius: '16px',
  }

  const hoverStyle = goldHover
    ? {
        border: '1px solid rgba(201, 168, 76, 0.4)',
        boxShadow: '0 0 24px rgba(201, 168, 76, 0.08)',
      }
    : {}

  return (
    <motion.div
      style={baseStyle}
      whileHover={goldHover ? hoverStyle : undefined}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      onClick={onClick}
      className={className}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick(e) : undefined}
    >
      {children}
    </motion.div>
  )
}

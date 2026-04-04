/**
 * MonoChip — Nakshatra bracketed status chip.
 *
 * Renders text in DM Mono, uppercase, inside brackets.
 * Example output: [ON TRACK]  [LEVEL 07]  [MISSED]
 *
 * Props:
 *   text    — chip label (will be uppercased automatically)
 *   color   — 'gold' | 'blue' | 'red' | 'white' | 'dim'
 */

const COLOR_MAP = {
  gold: {
    color: '#C9A84C',
    background: 'rgba(201,168,76,0.08)',
    border: '1px solid rgba(201,168,76,0.25)',
  },
  blue: {
    color: '#4A6FA5',
    background: 'rgba(74,111,165,0.08)',
    border: '1px solid rgba(74,111,165,0.25)',
  },
  red: {
    color: '#C47474',
    background: 'rgba(196,116,116,0.08)',
    border: '1px solid rgba(196,116,116,0.25)',
  },
  white: {
    color: '#F0EDE6',
    background: 'rgba(240,237,230,0.05)',
    border: '1px solid rgba(240,237,230,0.15)',
  },
  dim: {
    color: 'rgba(240,237,230,0.35)',
    background: 'transparent',
    border: '1px solid rgba(240,237,230,0.1)',
  },
}

export default function MonoChip({ text, color = 'gold' }) {
  const styles = COLOR_MAP[color] || COLOR_MAP.gold

  return (
    <span
      style={{
        fontFamily: '"DM Mono", monospace',
        fontSize: '0.65rem',
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        borderRadius: '9999px',
        padding: '2px 10px',
        display: 'inline-flex',
        alignItems: 'center',
        lineHeight: 1.6,
        whiteSpace: 'nowrap',
        ...styles,
      }}
    >
      [{text?.toUpperCase()}]
    </span>
  )
}

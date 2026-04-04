/**
 * LoadingVoid — Full-screen loading overlay.
 *
 * Props:
 *   text — optional DM Mono label shown below the pulsing dot
 */
export default function LoadingVoid({ text = 'loading...' }) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: '#08090F',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '20px',
        zIndex: 9999,
      }}
    >
      {/* Pulsing gold dot */}
      <div
        style={{
          width: '12px',
          height: '12px',
          borderRadius: '50%',
          background: '#C9A84C',
          animation: 'pulseGold 2s ease-in-out infinite',
        }}
      />

      {/* Label */}
      {text && (
        <span
          style={{
            fontFamily: '"DM Mono", monospace',
            fontSize: '0.7rem',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'rgba(240,237,230,0.35)',
          }}
        >
          {text}
        </span>
      )}
    </div>
  )
}

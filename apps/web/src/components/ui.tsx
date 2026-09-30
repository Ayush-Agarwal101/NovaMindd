import type { CSSProperties } from 'react'

// ── Shared style constants ───────────────────────────────────────────────────
export const S = {
  card: {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: 10,
    padding: 20,
  } as CSSProperties,

  cardSm: {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: 8,
    padding: 14,
  } as CSSProperties,

  input: {
    background: 'var(--color-surface2)',
    border: '1px solid var(--color-border)',
    borderRadius: 7,
    padding: '9px 12px',
    color: 'var(--color-text)',
    fontSize: 13.5,
    width: '100%',
    outline: 'none',
  } as CSSProperties,

  btn: {
    background: 'var(--color-accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 7,
    padding: '9px 18px',
    fontSize: 13.5,
    fontWeight: 600,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
  } as CSSProperties,

  btnGhost: {
    background: 'var(--color-surface2)',
    color: 'var(--color-text)',
    border: '1px solid var(--color-border)',
    borderRadius: 7,
    padding: '8px 16px',
    fontSize: 13,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
  } as CSSProperties,

  label: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--color-muted)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
    marginBottom: 6,
    display: 'block',
  } as CSSProperties,

  section: {
    marginBottom: 28,
  } as CSSProperties,

  grid2: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 16,
  } as CSSProperties,

  grid3: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr 1fr',
    gap: 16,
  } as CSSProperties,
}

// ── Badge ────────────────────────────────────────────────────────────────────
const BADGE_COLORS: Record<string, CSSProperties> = {
  loaded:    { background: 'rgba(16,185,129,0.15)', color: '#10b981' },
  available: { background: 'rgba(99,102,241,0.15)', color: '#818cf8' },
  enabled:   { background: 'rgba(16,185,129,0.15)', color: '#10b981' },
  disabled:  { background: 'rgba(239,68,68,0.15)',  color: '#ef4444' },
  error:     { background: 'rgba(239,68,68,0.15)',  color: '#ef4444' },
  completed: { background: 'rgba(16,185,129,0.15)', color: '#10b981' },
  failed:    { background: 'rgba(239,68,68,0.15)',  color: '#ef4444' },
  fail_closed: { background: 'rgba(245,158,11,0.15)', color: '#f59e0b' },
  running:   { background: 'rgba(99,102,241,0.15)', color: '#818cf8' },
  ok:        { background: 'rgba(16,185,129,0.15)', color: '#10b981' },
  unknown:   { background: 'rgba(124,133,168,0.15)', color: '#7c85a8' },
}

export function Badge({ label }: { label: string }) {
  const lower = label.toLowerCase()
  const style = BADGE_COLORS[lower] ?? BADGE_COLORS.unknown
  return (
    <span
      style={{
        ...style,
        borderRadius: 5,
        padding: '2px 8px',
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}

// ── Spinner ──────────────────────────────────────────────────────────────────
export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        border: `2px solid var(--color-border)`,
        borderTopColor: 'var(--color-accent)',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}
    />
  )
}

// ── Error banner ─────────────────────────────────────────────────────────────
export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      style={{
        background: 'rgba(239,68,68,0.1)',
        border: '1px solid rgba(239,68,68,0.3)',
        borderRadius: 8,
        padding: '12px 16px',
        color: '#ef4444',
        fontSize: 13,
        marginBottom: 16,
      }}
    >
      {message}
    </div>
  )
}

// ── Section header ───────────────────────────────────────────────────────────
export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text)', marginBottom: 4 }}>
        {title}
      </h2>
      {subtitle && (
        <p style={{ fontSize: 13, color: 'var(--color-muted)' }}>{subtitle}</p>
      )}
    </div>
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────
export function EmptyState({ message }: { message: string }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '40px 20px',
        color: 'var(--color-muted)',
        fontSize: 13,
      }}
    >
      {message}
    </div>
  )
}

// ── Stat card ────────────────────────────────────────────────────────────────
export function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string | number
  sub?: string
  accent?: boolean
}) {
  return (
    <div
      style={{
        ...S.card,
        borderColor: accent ? 'var(--color-accent)' : 'var(--color-border)',
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: accent ? 'var(--color-accent-hover)' : 'var(--color-text)', lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 6 }}>{sub}</div>
      )}
    </div>
  )
}

// Inject keyframes once
const spinStyle = document.createElement('style')
spinStyle.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
document.head.appendChild(spinStyle)

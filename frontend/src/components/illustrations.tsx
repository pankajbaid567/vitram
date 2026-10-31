/** Decorative inline-SVG illustrations in the VITRAM glass style. All are aria-hidden: they never carry information.
 * No brand marks of real banks or insurers appear here. */
import clsx from 'clsx'
import { useId } from 'react'

type P = { className?: string }

/** Soft mountain horizon that sits behind page headers. */
export function Horizon({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 1200 260" preserveAspectRatio="xMidYMax slice" className={clsx('pointer-events-none select-none', className)} aria-hidden>
      <defs>
        <linearGradient id={`${id}s`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#fbe6c8" stopOpacity="0" />
          <stop offset="0.7" stopColor="#f6dcc0" stopOpacity="0.55" />
          <stop offset="1" stopColor="#e9e3f7" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${id}a`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#b9c0f1" /><stop offset="1" stopColor="#dfe2fa" stopOpacity="0" /></linearGradient>
        <linearGradient id={`${id}b`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#a3aceb" /><stop offset="1" stopColor="#dde0fa" stopOpacity="0" /></linearGradient>
        <linearGradient id={`${id}c`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#8f99e3" stopOpacity="0.8" /><stop offset="1" stopColor="#e2e5fb" stopOpacity="0" /></linearGradient>
      </defs>
      <rect x="0" y="40" width="1200" height="180" fill={`url(#${id}s)`} />
      <circle cx="930" cy="120" r="26" fill="#fff4e0" opacity="0.9" />
      <path d="M0 200 L140 120 L230 170 L360 80 L470 160 L560 110 L700 190 L820 100 L930 150 L1040 70 L1200 170 L1200 260 L0 260Z" fill={`url(#${id}a)`} opacity="0.55" />
      <path d="M0 230 L120 170 L260 215 L420 140 L560 205 L700 150 L860 215 L1000 150 L1200 220 L1200 260 L0 260Z" fill={`url(#${id}b)`} opacity="0.6" />
      <path d="M0 250 L180 205 L330 240 L520 195 L720 245 L900 205 L1080 240 L1200 215 L1200 260 L0 260Z" fill={`url(#${id}c)`} opacity="0.55" />
    </svg>
  )
}

/** Wave lines for the sidebar foot. */
export function SidebarWave({ className }: P) {
  return (
    <svg viewBox="0 0 260 180" className={clsx('pointer-events-none', className)} aria-hidden fill="none">
      {Array.from({ length: 9 }).map((_, i) => (
        <path key={i} d={`M-10 ${150 - i * 6} C 60 ${110 - i * 9}, 130 ${170 - i * 4}, 270 ${60 - i * 6}`} stroke="#8f9bff" strokeOpacity={0.08 + i * 0.025} strokeWidth="1.2" />
      ))}
    </svg>
  )
}

function GlassDefs({ id }: { id: string }) {
  return (
    <defs>
      <linearGradient id={`${id}g`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffffff" stopOpacity="0.95" /><stop offset="1" stopColor="#dfe3fb" stopOpacity="0.75" /></linearGradient>
      <linearGradient id={`${id}i`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6d7cf0" /><stop offset="1" stopColor="#3443b5" /></linearGradient>
      <linearGradient id={`${id}n`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3a47b8" /><stop offset="1" stopColor="#161d52" /></linearGradient>
      <radialGradient id={`${id}f`} cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#9aa4f0" stopOpacity="0.45" /><stop offset="1" stopColor="#9aa4f0" stopOpacity="0" /></radialGradient>
      <filter id={`${id}s`} x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#3443b5" floodOpacity="0.18" /></filter>
    </defs>
  )
}

/** Stacked statement pages with small category chips (bank-statement upload). */
export function DocStack({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 220 180" className={className} aria-hidden>
      <GlassDefs id={id} />
      <ellipse cx="110" cy="92" rx="100" ry="80" fill={`url(#${id}f)`} />
      <g filter={`url(#${id}s)`}>
        <rect x="70" y="26" width="104" height="132" rx="14" fill="#e4e8fc" transform="rotate(10 122 92)" />
        <rect x="58" y="22" width="104" height="132" rx="14" fill={`url(#${id}g)`} stroke="#fff" transform="rotate(-4 110 88)" />
      </g>
      <g transform="rotate(-4 110 88)">
        {[48, 62, 76, 90, 104, 118].map((y, i) => <rect key={y} x="74" y={y} width={i % 2 ? 56 : 72} height="6" rx="3" fill="#c7cdf5" />)}
        <rect x="74" y="34" width="40" height="8" rx="4" fill={`url(#${id}i)`} />
      </g>
      <circle cx="52" cy="70" r="15" fill="#fff" filter={`url(#${id}s)`} /><path d="M46 70h12M52 64v12" stroke="#3443b5" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="170" cy="128" r="15" fill="#fff" filter={`url(#${id}s)`} /><path d="M164 128l4 4 8-8" stroke="#17744a" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="62" cy="126" r="12" fill="#fff" filter={`url(#${id}s)`} /><circle cx="62" cy="126" r="4.5" fill="#e7a02f" />
    </svg>
  )
}

/** Shield with umbrella (insurance). */
export function ShieldArt({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 260 220" className={className} aria-hidden>
      <GlassDefs id={id} />
      <ellipse cx="130" cy="110" rx="120" ry="100" fill={`url(#${id}f)`} />
      <ellipse cx="130" cy="196" rx="70" ry="12" fill="#c9cff6" opacity="0.7" />
      <path d="M130 26 L196 50 V110 C196 150 166 178 130 192 C94 178 64 150 64 110 V50 Z" fill={`url(#${id}g)`} stroke="#fff" strokeWidth="2" filter={`url(#${id}s)`} />
      <path d="M130 44 L182 62 V110 C182 142 158 164 130 176 C102 164 78 142 78 110 V62 Z" fill="#e7eafd" opacity="0.8" />
      <path d="M98 108 C98 88 112 76 130 76 C148 76 162 88 162 108 Z" fill={`url(#${id}i)`} />
      <path d="M130 108 V140 C130 148 120 148 120 140" stroke="#3443b5" strokeWidth="4" fill="none" strokeLinecap="round" />
      <circle cx="44" cy="96" r="20" fill="#fff" filter={`url(#${id}s)`} /><path d="M36 95c0-4 3-7 6-7 2 0 3 1 2 2 1-1 2-2 4-2 3 0 6 3 6 7 0 6-10 11-10 11s-8-5-8-11z" fill="#d64545" />
      <circle cx="214" cy="60" r="20" fill="#fff" filter={`url(#${id}s)`} /><circle cx="208" cy="55" r="4" fill="#17744a" /><circle cx="221" cy="55" r="4" fill="#17744a" opacity="0.75" /><path d="M200 70c0-6 16-6 16 0z" fill="#17744a" /><path d="M214 70c0-6 15-6 15 0z" fill="#17744a" opacity="0.75" />
      <circle cx="206" cy="160" r="18" fill="#fff" filter={`url(#${id}s)`} /><rect x="199" y="151" width="14" height="18" rx="2.5" fill="none" stroke="#3443b5" strokeWidth="2.2" /><path d="M202 157h8M202 162h8" stroke="#3443b5" strokeWidth="2" />
    </svg>
  )
}

/** Fanned generic cards; the front card carries the VITRAM mark only. */
export function CardStackArt({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 300 200" className={className} aria-hidden>
      <GlassDefs id={id} />
      <ellipse cx="160" cy="110" rx="140" ry="90" fill={`url(#${id}f)`} />
      <ellipse cx="170" cy="120" rx="120" ry="30" fill="none" stroke="#e7a02f" strokeOpacity="0.45" strokeWidth="1.5" transform="rotate(-12 170 120)" />
      <g filter={`url(#${id}s)`}>
        <rect x="70" y="30" width="150" height="94" rx="14" fill={`url(#${id}g)`} stroke="#fff" transform="rotate(-14 145 77)" />
        <rect x="96" y="44" width="150" height="94" rx="14" fill="#dfe3fb" stroke="#fff" transform="rotate(-8 171 91)" />
        <rect x="112" y="70" width="156" height="98" rx="16" fill={`url(#${id}n)`} transform="rotate(-12 190 119)" />
      </g>
      <g transform="rotate(-12 190 119)">
        <rect x="130" y="100" width="26" height="20" rx="4" fill="#f0d08a" />
        <path d="M232 86l9 15 9-15" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="130" y="138" width="80" height="6" rx="3" fill="#fff" opacity="0.35" />
        <rect x="130" y="150" width="50" height="6" rx="3" fill="#fff" opacity="0.25" />
      </g>
    </svg>
  )
}

/** Small house with coin stacks (loans). */
export function HouseArt({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 240 180" className={className} aria-hidden>
      <GlassDefs id={id} />
      <ellipse cx="120" cy="96" rx="110" ry="80" fill={`url(#${id}f)`} />
      <rect x="120" y="22" width="96" height="72" rx="10" fill={`url(#${id}g)`} stroke="#fff" transform="rotate(6 168 58)" filter={`url(#${id}s)`} />
      <path d="M134 74 L150 60 L164 68 L184 44 L200 54" stroke="#6d7cf0" strokeWidth="2.5" fill="none" strokeLinecap="round" transform="rotate(6 168 58)" />
      <g filter={`url(#${id}s)`}>
        <path d="M40 100 L86 62 L132 100 V150 H40 Z" fill={`url(#${id}g)`} stroke="#fff" />
        <path d="M32 104 L86 58 L140 104" stroke={`url(#${id}i)`} strokeWidth="10" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="74" y="118" width="24" height="32" rx="4" fill={`url(#${id}i)`} />
      </g>
      {[0, 1, 2, 3].map((i) => <ellipse key={i} cx="170" cy={150 - i * 8} rx="20" ry="7" fill={i === 3 ? '#f3c35e' : '#e7a02f'} stroke="#c9861c" strokeWidth="1" />)}
      {[0, 1, 2].map((i) => <ellipse key={i} cx="204" cy={152 - i * 8} rx="16" ry="6" fill={i === 2 ? '#f3c35e' : '#e7a02f'} stroke="#c9861c" strokeWidth="1" />)}
    </svg>
  )
}

/** Account holder with family members orbiting (family). */
export function FamilyArt({ className }: P) {
  const id = useId()
  const person = (cx: number, cy: number, r: number, fill: string) => (
    <g>
      <circle cx={cx} cy={cy} r={r} fill="#fff" filter={`url(#${id}s)`} />
      <circle cx={cx} cy={cy - r * 0.18} r={r * 0.3} fill={fill} />
      <path d={`M${cx - r * 0.5} ${cy + r * 0.55} C${cx - r * 0.5} ${cy + r * 0.12} ${cx + r * 0.5} ${cy + r * 0.12} ${cx + r * 0.5} ${cy + r * 0.55}`} fill={fill} />
    </g>
  )
  return (
    <svg viewBox="0 0 300 180" className={className} aria-hidden>
      <GlassDefs id={id} />
      <ellipse cx="150" cy="90" rx="140" ry="85" fill={`url(#${id}f)`} />
      <ellipse cx="150" cy="96" rx="120" ry="48" fill="none" stroke="#a9b2f0" strokeOpacity="0.6" strokeWidth="1.2" transform="rotate(-8 150 96)" />
      <circle cx="150" cy="90" r="52" fill={`url(#${id}g)`} stroke="#fff" strokeWidth="2" filter={`url(#${id}s)`} />
      <circle cx="150" cy="78" r="16" fill={`url(#${id}i)`} />
      <path d="M124 122 C124 98 176 98 176 122 Z" fill={`url(#${id}i)`} />
      {person(62, 58, 24, '#8f80f7')}
      {person(98, 132, 22, '#27a876')}
      {person(238, 52, 24, '#e7a02f')}
    </svg>
  )
}

/** Stacked list tile on a glass base (EMIs empty). */
export function ListTileArt({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 200 150" className={className} aria-hidden>
      <GlassDefs id={id} />
      <ellipse cx="100" cy="118" rx="80" ry="16" fill="#dfe3fb" />
      <ellipse cx="100" cy="112" rx="64" ry="12" fill="#fff" opacity="0.9" />
      <rect x="62" y="20" width="76" height="90" rx="16" fill={`url(#${id}g)`} stroke="#fff" filter={`url(#${id}s)`} />
      <rect x="74" y="34" width="52" height="56" rx="10" fill={`url(#${id}i)`} opacity="0.9" />
      {[46, 60, 74].map((y) => <g key={y}><circle cx="84" cy={y} r="3" fill="#fff" /><rect x="92" y={y - 2.5} width="26" height="5" rx="2.5" fill="#fff" opacity="0.9" /></g>)}
    </svg>
  )
}

/** Small journey-card scenery: layered peaks in a hue. */
export function PeaksArt({ hue = 'indigo', className }: P & { hue?: 'indigo' | 'green' | 'violet' | 'amber' }) {
  const id = useId()
  const c = { indigo: ['#c3c9f3', '#8f99e3'], green: ['#bfe8d3', '#5fbf8f'], violet: ['#ddd3fb', '#a996f2'], amber: ['#fde0b8', '#f0a553'] }[hue]
  return (
    <svg viewBox="0 0 140 90" className={className} aria-hidden>
      <defs><linearGradient id={`${id}p`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={c[1]} /><stop offset="1" stopColor={c[0]} stopOpacity="0" /></linearGradient></defs>
      <path d="M0 90 L30 52 L52 70 L84 22 L112 60 L140 40 L140 90 Z" fill={c[0]} opacity="0.7" />
      <path d="M10 90 L48 48 L70 66 L96 36 L140 90 Z" fill={`url(#${id}p)`} />
    </svg>
  )
}

import clsx from 'clsx'
import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'saathi' | 'quiet'
type Size = 'sm' | 'md' | 'lg'

const base =
  'inline-flex items-center justify-center gap-2 font-medium rounded-[var(--radius-control)] select-none whitespace-nowrap ' +
  'transition-[background-color,box-shadow,transform,color,border-color] duration-[var(--dur)] ease-[var(--ease-out-soft)] ' +
  'active:translate-y-px active:scale-[0.985] disabled:opacity-55 disabled:active:translate-y-0 disabled:active:scale-100'
const variants: Record<Variant, string> = {
  // Primary actions stay solid for contrast — never translucent.
  primary: 'bg-[image:var(--grad-indigo)] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18),0_1px_2px_rgb(22_29_69/0.2),0_6px_16px_rgb(52_67_181/0.28)] hover:brightness-110 hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.2),0_2px_4px_rgb(22_29_69/0.2),0_10px_24px_rgb(52_67_181/0.34)]',
  secondary: 'bg-white/90 text-ink border border-[var(--glass-hairline)] shadow-[var(--glass-highlight),var(--elev-1)] hover:border-indigo/40 hover:text-indigo-dark hover:shadow-[var(--glass-highlight),var(--elev-2)]',
  ghost: 'text-indigo hover:bg-indigo-soft',
  quiet: 'text-muted hover:text-ink hover:bg-ink/5',
  danger: 'bg-critical text-white shadow-[0_6px_16px_rgb(179_38_30/0.25)] hover:brightness-110',
  saathi: 'bg-[image:var(--grad-saathi)] text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.35),var(--glow-saathi)] hover:brightness-105',
}
const sizes: Record<Size, string> = {
  sm: 'min-h-9 px-3 text-sm',
  md: 'min-h-11 px-4 text-[0.95rem]',
  lg: 'min-h-12 px-5 text-base',
}

export function buttonClass(variant: Variant = 'primary', size: Size = 'md', className?: string) {
  return clsx(base, variants[variant], sizes[size], className)
}

export function Button({
  variant = 'primary', size = 'md', loading, icon, children, className, type = 'button', disabled, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode }) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
}

export function LinkButton({
  variant = 'primary', size = 'md', icon, children, className, ...rest
}: LinkProps & { variant?: Variant; size?: Size; icon?: ReactNode }) {
  return (
    <Link className={buttonClass(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  )
}

export function IconButton({ label, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" aria-label={label} title={label}
      className={clsx('inline-flex size-11 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-ink/5 hover:text-ink', className)}
      {...rest}>
      {children}
    </button>
  )
}

import clsx from 'clsx'
import { Eye, EyeOff } from 'lucide-react'
import { cloneElement, isValidElement, useId, useState, type InputHTMLAttributes, type ReactElement, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

const control =
  'w-full min-h-11 rounded-[var(--radius-control)] border border-line-strong/80 bg-white/90 px-3.5 text-base text-ink shadow-[inset_0_1px_2px_rgb(22_29_69/0.04)] ' +
  'placeholder:text-muted/70 transition-[border-color,box-shadow] duration-[var(--dur-fast)] hover:border-line-strong ' +
  'focus:border-indigo focus:outline-none focus:shadow-[var(--ring)] aria-[invalid=true]:border-critical aria-[invalid=true]:focus:shadow-[0_0_0_3px_rgb(179_38_30/0.2)]'

/** Label + optional hint + inline error, wired with aria attributes. */
export function Field({ label, hint, error, optional, children, className }: {
  label: string; hint?: ReactNode; error?: string | null; optional?: boolean; children: ReactElement<any>; className?: string
}) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errId = error ? `${id}-err` : undefined
  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<any>, {
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': [hintId, errId].filter(Boolean).join(' ') || undefined,
      })
    : children
  return (
    <div className={clsx('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {optional && <span className="ml-1.5 font-normal text-muted">(optional)</span>}
      </label>
      {child}
      {hint && !error && <p id={hintId} className="text-sm text-muted">{hint}</p>}
      {error && <p id={errId} className="text-sm text-critical" role="alert">{error}</p>}
    </div>
  )
}

export function Input({ className, prefix, ...rest }: InputHTMLAttributes<HTMLInputElement> & { prefix?: string }) {
  if (prefix) {
    return (
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted" aria-hidden>{prefix}</span>
        <input className={clsx(control, 'pl-7 num', className)} {...rest} />
      </div>
    )
  }
  return <input className={clsx(control, className)} {...rest} />
}

/** Password input with a show/hide toggle. Receives id/aria props from <Field> like any input. */
export function PasswordInput({ className, ...rest }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input type={show ? 'text' : 'password'} className={clsx(control, 'pr-12', className)} {...rest} />
      <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}
        className="absolute inset-y-0 right-1 my-auto inline-flex size-10 items-center justify-center rounded-[10px] text-muted transition-colors hover:bg-ink/5 hover:text-ink">
        {show ? <EyeOff className="size-[1.1rem]" aria-hidden /> : <Eye className="size-[1.1rem]" aria-hidden />}
      </button>
    </div>
  )
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(control, 'appearance-none bg-[url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2712%27 height=%2712%27 viewBox=%270 0 24 24%27 fill=%27none%27 stroke=%27%235b6280%27 stroke-width=%272.5%27%3E%3Cpath d=%27m6 9 6 6 6-6%27/%3E%3C/svg%3E")] bg-[position:right_0.75rem_center] bg-no-repeat pr-9', className)} {...rest}>
      {children}
    </select>
  )
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(control, 'min-h-24 py-2', className)} {...rest} />
}

export function Checkbox({ label, description, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; description?: ReactNode }) {
  const id = useId()
  return (
    <div className={clsx('flex items-start gap-3', className)}>
      <input id={id} type="checkbox" className="mt-0.5 size-5 shrink-0 accent-indigo" {...rest} />
      <label htmlFor={id} className="text-[0.95rem] leading-snug">
        {label}
        {description && <span className="mt-0.5 block text-sm text-muted">{description}</span>}
      </label>
    </div>
  )
}

/** Accessible segmented control (radio group). */
export function Segmented<T extends string | number>({ value, onChange, options, label, name }: {
  value: T | null; onChange: (v: T) => void; options: { value: T; label: string; hint?: string }[]; label: string; name?: string
}) {
  const id = useId()
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{label}</legend>
      <div className="inline-flex flex-wrap gap-2" role="radiogroup">
        {options.map((o) => {
          const checked = value === o.value
          return (
            <label key={String(o.value)}
              className={clsx('flex min-h-11 items-center gap-2 rounded-[var(--radius-control)] border px-4 text-[0.95rem] transition-[background-color,border-color,box-shadow] duration-[var(--dur)] has-[:focus-visible]:shadow-[var(--ring)]',
                checked ? 'border-indigo/50 bg-indigo-soft text-indigo-dark font-medium shadow-[inset_0_0_0_1px_rgb(52_67_181/0.25)]' : 'border-line-strong/80 bg-white/90 hover:border-indigo/50')}>
              <input type="radio" className="sr-only" name={name ?? id} checked={checked} onChange={() => onChange(o.value)} />
              {o.label}
              {o.hint && <span className="text-sm text-muted">{o.hint}</span>}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

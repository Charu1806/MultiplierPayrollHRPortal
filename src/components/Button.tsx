import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  children: ReactNode
}

const variants: Record<Variant, string> = {
  primary:
    'bg-text-primary text-white border border-transparent hover:bg-slate-800 disabled:opacity-50',
  secondary:
    'bg-surface text-text-primary border border-border hover:bg-surface-recessed disabled:opacity-50',
  ghost:
    'bg-transparent text-text-secondary border border-transparent hover:bg-surface-recessed hover:text-text-primary disabled:opacity-50',
}

export function Button({
  variant = 'primary',
  className = '',
  children,
  type = 'button',
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={`inline-flex h-8 items-center justify-center rounded px-3 text-xs font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-text-primary ${variants[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

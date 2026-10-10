/** Reuses the tab favicon at /public/favicon.svg — do not redraw. */
const FAVICON = '/favicon.svg'

type Props = {
  size?: number
  className?: string
  alt?: string
}

export function MultiplierLogo({ size = 18, className = '', alt = 'Multiplier' }: Props) {
  return (
    <img
      src={FAVICON}
      width={size}
      height={size}
      alt={alt}
      className={`inline-block shrink-0 object-contain ${className}`}
      style={{ width: size, height: size }}
    />
  )
}

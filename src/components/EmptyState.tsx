type Props = {
  title: string
  description?: string
}

export function EmptyState({ title, description }: Props) {
  return (
    <div className="rounded border border-border bg-surface px-6 py-10 text-center">
      <p className="text-sm font-medium text-text-primary">{title}</p>
      {description ? (
        <p className="mt-1 text-xs text-text-secondary">{description}</p>
      ) : null}
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Button, StatusChip } from '@/components'
import { clarityApi } from '@/api/clarityClient'
import { DrivePickCancelled, googleDriveReady, pickDriveFile } from '@/lib/googleDrive'
import { useAppStore } from '@/store'
import type { MappingRowDto } from '@/api/types'

export type DocType =
  | 'Offer letter'
  | 'Bonus letter'
  | 'Reimbursement bill'
  | 'Salary revision letter'
  | 'Resignation / exit letter'
  | 'Other'

type InputSource = 'upload' | 'demo' | 'gdrive'

const HELPERS: Record<DocType, string> = {
  'Offer letter': "We'll read name, job title, start date and salary.",
  'Bonus letter': "We'll read the amount, type and pay month.",
  'Reimbursement bill': "We'll read the amount, date and what it was for.",
  'Salary revision letter':
    "We'll read the new monthly salary. The salary issue closes once this letter is stored.",
  'Resignation / exit letter': "We'll read last working day and notice details.",
  Other: "We'll extract any payroll fields we can find.",
}

/** Demo presets (seed PDFs) — same attach pipeline as any upload. */
const DEMO_BY_TYPE: Record<DocType, { file: string; label: string }[]> = {
  'Offer letter': [
    { file: 'offer_letter_priya.pdf', label: 'Demo · India offer (Priya)' },
    { file: 'offer_letter_arjun.pdf', label: 'Demo · India offer (Arjun)' },
  ],
  'Bonus letter': [{ file: 'bonus_letter_james.pdf', label: 'Demo · UK bonus (James)' }],
  'Reimbursement bill': [
    { file: 'travel_reimbursement_chloe.pdf', label: 'Demo · UK reimbursement (Chloe)' },
  ],
  'Salary revision letter': [
    { file: 'salary_revision_james_patel.pdf', label: 'Demo · UK salary revision (James)' },
  ],
  'Resignation / exit letter': [],
  Other: [
    { file: 'offer_letter_priya.pdf', label: 'Demo · India offer' },
    { file: 'bonus_letter_james.pdf', label: 'Demo · UK bonus' },
  ],
}

function namesMatch(a: string, b: string) {
  const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')
  return norm(a) === norm(b)
}

type Props = {
  employeeId?: string
  /** When set, flag if document employee name differs */
  employeeName?: string
  defaultType?: DocType
  /** Keep the document type fixed. The caller already chose hike or bonus. */
  lockType?: boolean
  /** Compact: only Upload / Demo / Drive (for one-time payments) */
  compact?: boolean
  onExtracted?: (fileName: string, mappings: MappingRowDto[]) => void
  onMappingsChange?: (mappings: MappingRowDto[]) => void
}

export function DriveAttach({
  employeeId,
  employeeName,
  defaultType = 'Offer letter',
  lockType = false,
  compact = false,
  onExtracted,
  onMappingsChange,
}: Props) {
  const asOf = useAppStore((s) => s.asOf)
  const pushToast = useAppStore((s) => s.pushToast)
  const loadEmployee = useAppStore((s) => s.loadEmployee)
  const refreshAll = useAppStore((s) => s.refreshAll)
  const [docType, setDocType] = useState<DocType>(defaultType)
  const [source, setSource] = useState<InputSource | null>(compact ? null : 'demo')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [mappings, setMappings] = useState<MappingRowDto[] | null>(null)
  const [nameMismatch, setNameMismatch] = useState<string | null>(null)
  const googleReady = googleDriveReady()
  const demos = useMemo(() => DEMO_BY_TYPE[docType], [docType])

  useEffect(() => {
    setDocType(defaultType)
  }, [defaultType])

  function setMaps(next: MappingRowDto[] | null) {
    setMappings(next)
    if (next) onMappingsChange?.(next)
    if (employeeName && next) {
      const nameRow = next.find((m) =>
        /employee name|legal name/i.test(m.multiplierField || ''),
      )
      const docName = (nameRow?.value || '').trim()
      if (
        docName &&
        docName.toLowerCase() !== 'not found' &&
        !namesMatch(docName, employeeName)
      ) {
        setNameMismatch(docName)
      } else {
        setNameMismatch(null)
      }
    } else {
      setNameMismatch(null)
    }
  }

  async function extract(name: string, fileId?: string, accessToken?: string) {
    setBusy(true)
    try {
      const result = await clarityApi.extractDrive({
        fileName: name,
        fileId,
        accessToken,
        employeeId,
        asOf,
      })
      setFileName(name)
      setMaps(result.mappings)
      setNote(result.fallbackNote || null)
      if (employeeId) {
        await loadEmployee(employeeId)
        await refreshAll()
      }
      onExtracted?.(name, result.mappings)
      if (result.usedFallback) pushToast('Used saved extraction')
    } catch (err) {
      pushToast(err instanceof Error ? err.message : 'Could not extract document')
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(file: File) {
    setBusy(true)
    try {
      const result = await clarityApi.extractUpload(file, { employeeId, asOf })
      setFileName(file.name)
      setMaps(result.mappings)
      setNote(result.fallbackNote || null)
      if (employeeId) {
        await loadEmployee(employeeId)
        await refreshAll()
      }
      onExtracted?.(file.name, result.mappings)
      if (result.usedFallback) pushToast('Fields filled from document — review and submit')
    } catch (err) {
      const known = Object.values(DEMO_BY_TYPE)
        .flat()
        .some((d) => d.file === file.name)
      if (known) {
        await extract(file.name)
        return
      }
      pushToast(err instanceof Error ? err.message : 'Could not upload document')
    } finally {
      setBusy(false)
    }
  }

  const sources: { id: InputSource; label: string; hint: string; disabled?: boolean }[] = [
    { id: 'upload', label: 'Upload', hint: 'From computer' },
    { id: 'demo', label: 'Demo', hint: 'Preset document' },
    {
      id: 'gdrive',
      label: 'Google Drive',
      hint: googleReady ? 'Sign in' : 'Not set up',
      disabled: !googleReady,
    },
  ]

  return (
    <div className="space-y-3 rounded border border-border bg-surface p-3">
      {!compact && !lockType ? (
        <>
          <label className="block text-xs text-text-secondary">
            Document type
            <select
              className="mt-1 h-8 w-full rounded border border-border bg-surface px-2 text-xs text-text-primary"
              value={docType}
              onChange={(e) => setDocType(e.target.value as DocType)}
            >
              {(Object.keys(HELPERS) as DocType[]).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <p className="text-[11px] text-text-muted">{HELPERS[docType]}</p>
        </>
      ) : (
        <p className="text-[11px] text-text-muted">{HELPERS[docType]}</p>
      )}

      <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
        Input from
      </p>
      <div className="grid grid-cols-3 gap-2">
        {sources.map((opt) => {
          const selected = source === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              data-testid={`doc-source-${opt.id}`}
              disabled={opt.disabled || busy}
              onClick={() => setSource(opt.id)}
              className={[
                'rounded border px-2 py-2 text-left text-[12px] transition',
                selected
                  ? 'border-text-primary bg-surface-recessed'
                  : 'border-border bg-surface hover:bg-surface-recessed',
                opt.disabled ? 'cursor-not-allowed opacity-50' : '',
              ].join(' ')}
            >
              <span className="font-medium text-text-primary">{opt.label}</span>
              <span className="mt-0.5 block text-[10px] text-text-muted">{opt.hint}</span>
            </button>
          )
        })}
      </div>

      {source === 'upload' ? (
        <label className="inline-flex h-8 cursor-pointer items-center rounded border border-border bg-surface px-3 text-xs hover:bg-surface-recessed">
          {busy ? 'Reading…' : 'Upload from computer'}
          <input
            type="file"
            accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf"
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void onUpload(f)
              e.target.value = ''
            }}
          />
        </label>
      ) : null}

      {source === 'demo' ? (
        <select
          className="h-8 w-full rounded border border-border bg-surface px-2 text-xs"
          disabled={busy || demos.length === 0}
          defaultValue=""
          aria-label="Demo document"
          onChange={(e) => {
            const v = e.target.value
            if (v) void extract(v)
            e.target.value = ''
          }}
        >
          <option value="">Choose demo document…</option>
          {demos.map((d) => (
            <option key={d.file} value={d.file}>
              {d.label}
            </option>
          ))}
        </select>
      ) : null}

      {source === 'gdrive' ? (
        <div>
          <Button
            variant="secondary"
            disabled={busy || !googleReady}
            onClick={() => {
              void (async () => {
                setBusy(true)
                try {
                  const picked = await pickDriveFile()
                  await extract(picked.fileName, picked.fileId, picked.accessToken)
                } catch (err) {
                  if (err instanceof DrivePickCancelled) return
                  pushToast(err instanceof Error ? err.message : 'Could not open Google sign-in')
                } finally {
                  setBusy(false)
                }
              })()
            }}
          >
            {busy ? 'Waiting for Google…' : 'Sign in with Google'}
          </Button>
          <p className="mt-1 text-[11px] text-text-muted">
            {googleReady
              ? 'A Google window opens to sign in. Then pick a PDF, Word file, or image.'
              : 'Google Drive not set up – see README'}
          </p>
        </div>
      ) : null}

      {note ? <p className="text-[11px] text-text-muted">{note}</p> : null}

      {nameMismatch ? (
        <div
          className="rounded border border-status-danger-border bg-status-danger-bg px-3 py-2 text-[12px] text-status-danger-text"
          data-testid="name-mismatch"
        >
          Name mismatch — document says <strong>{nameMismatch}</strong>
          {employeeName ? (
            <>
              {' '}
              but this employee is <strong>{employeeName}</strong>.
            </>
          ) : null}{' '}
          Change the name below if this is the wrong person, or confirm if intentional.
        </div>
      ) : null}

      {mappings && fileName ? (
        <div>
          <p className="mb-1 text-[11px] text-text-secondary">
            Read from <em>{fileName}</em> · edit anything that looks wrong.
          </p>
          <table className="w-full table-fixed text-left text-[12px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-text-muted">
                <th className="py-1">Source field</th>
                <th>Multiplier field</th>
                <th>Value</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m, i) => {
                const isName = /employee name|legal name/i.test(m.multiplierField || '')
                const rowMismatch =
                  isName &&
                  nameMismatch &&
                  namesMatch(m.value || '', nameMismatch)
                return (
                  <tr key={i} className="border-t border-border">
                    <td className="py-1">{m.sourceField ?? '—'}</td>
                    <td>
                      {m.multiplierField}
                      {m.status === 'missing' ? (
                        <span className="ml-1 text-status-danger-text">✗</span>
                      ) : null}
                    </td>
                    <td>
                      <input
                        className={[
                          'h-7 w-full rounded border px-1.5 text-xs',
                          rowMismatch
                            ? 'border-status-danger-border bg-status-danger-bg'
                            : 'border-border',
                        ].join(' ')}
                        value={m.value}
                        onChange={(e) => {
                          const next = mappings.map((row, idx) =>
                            idx === i
                              ? {
                                  ...row,
                                  value: e.target.value,
                                  status: e.target.value.trim() ? 'mapped' : 'missing',
                                }
                              : row,
                          )
                          setMaps(next)
                        }}
                      />
                    </td>
                    <td>
                      {rowMismatch ? (
                        <StatusChip tone="danger">Mismatch</StatusChip>
                      ) : m.status === 'missing' ? (
                        <StatusChip tone="danger">Required</StatusChip>
                      ) : (
                        m.confidence || '—'
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {fileName ? (
            <p className="mt-2 text-[11px] text-text-secondary">
              Attached · <span className="font-medium">{fileName}</span> · View document
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

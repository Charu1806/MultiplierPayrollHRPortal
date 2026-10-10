import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, FileText, Loader2 } from 'lucide-react'
import { Button, PageHeader, StatusChip } from '@/components'
import { PeopleTabs } from '@/features/people/PeopleTabs'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { OFFER_DEMO_FILES, type OfferDemoFile } from '@/features/people/demoFiles'
import { clarityApi } from '@/api/clarityClient'
import { useAppStore } from '@/store'
import type { Country, ExtractResult, MappingRowDto } from '@/api/types'

type InputSource = 'upload' | 'gdrive' | 'demo'
type Phase = 'source' | 'fields' | 'processing' | 'missing' | 'done'

const emptyForm = {
  legalName: '',
  workEmail: '',
  workLocation: 'India' as Country,
  hireDate: '',
  monthlySalary: '',
  jobTitle: '',
  manager: '',
}

const JOURNEY: { key: string; label: string }[] = [
  { key: 'received', label: 'Received' },
  { key: 'read', label: 'Read document' },
  { key: 'mapped', label: 'Mapped' },
  { key: 'validated', label: 'Validated' },
  { key: 'cycle', label: 'Cycle assigned' },
  { key: 'stored', label: 'Stored' },
]

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

function applyMappingsToForm(mappings: MappingRowDto[]): Partial<typeof emptyForm> {
  const byField = Object.fromEntries(
    mappings.filter((m) => m.status === 'mapped' && m.value).map((m) => [m.multiplierField, m.value]),
  )
  const next: Partial<typeof emptyForm> = {}
  const name = byField['Employee name'] || byField['Legal name'] || ''
  if (name) next.legalName = String(name)
  const role = byField['Job title'] || ''
  if (role) next.jobTitle = String(role)
  const start = byField['Start date'] || byField['Hire date'] || ''
  if (start) {
    const raw = String(start)
    const iso = raw.match(/\d{4}-\d{2}-\d{2}/)?.[0]
    if (iso) {
      next.hireDate = iso
    } else {
      const parsed = Date.parse(raw)
      if (Number.isFinite(parsed)) {
        next.hireDate = new Date(parsed).toISOString().slice(0, 10)
      }
    }
  }
  const annual = byField['Annual gross salary']
  if (annual != null && String(annual).trim()) {
    const n = Number(String(annual).replace(/[,₹£€R$\s]/g, ''))
    if (Number.isFinite(n) && n > 0) next.monthlySalary = String(Math.round(n / 12))
  }
  const monthly = byField['Monthly base'] || byField['Salary'] || byField['Base salary']
  if (monthly != null && String(monthly).trim()) {
    const n = Number(String(monthly).replace(/[,₹£€R$\s]/g, ''))
    if (Number.isFinite(n) && n > 0) next.monthlySalary = String(n)
  }
  const manager = byField['Manager'] || ''
  if (manager) next.manager = String(manager)
  const country = byField['Country'] || byField['Work location'] || ''
  if (country === 'India' || country === 'UK' || country === 'Germany' || country === 'Brazil') {
    next.workLocation = country
  }
  return next
}

export function AddEmployeePage() {
  const navigate = useNavigate()
  const asOf = useAppStore((s) => s.asOf)
  const createEmployee = useAppStore((s) => s.createEmployee)
  const attachDocument = useAppStore((s) => s.attachDocument)
  const fillMissingFields = useAppStore((s) => s.fillMissingFields)
  const pushToast = useAppStore((s) => s.pushToast)

  const [source, setSource] = useState<InputSource | null>(null)
  const [phase, setPhase] = useState<Phase>('source')
  const [form, setForm] = useState(emptyForm)
  const [demoFile, setDemoFile] = useState<OfferDemoFile | ''>('')
  const [fileName, setFileName] = useState<string | null>(null)
  const [extractBusy, setExtractBusy] = useState(false)
  const [submitBusy, setSubmitBusy] = useState(false)
  const [activeStep, setActiveStep] = useState(-1)
  const [missing, setMissing] = useState<string[]>([])
  const [missingValues, setMissingValues] = useState<Record<string, string>>({})
  const [createdId, setCreatedId] = useState<string | null>(null)
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null)

  const googleReady = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID)

  function pickSource(s: InputSource) {
    setSource(s)
    setPhase('source')
    setFileName(null)
    setDemoFile('')
    setForm(emptyForm)
    setConfirmMsg(null)
    setMissing([])
    setCreatedId(null)
  }

  async function runExtract(name: string, file?: File) {
    setExtractBusy(true)
    try {
      let result: ExtractResult
      if (file) {
        result = await clarityApi.extractUpload(file, { asOf })
      } else {
        result = await clarityApi.extractDrive({ fileName: name, asOf })
      }
      setFileName(result.fileName || name)
      const filled = applyMappingsToForm(result.mappings || [])
      setForm((f) => ({
        ...f,
        ...filled,
        // Keep demo/email prefill when extract omits a field
        workEmail: filled.workEmail || f.workEmail,
        manager: filled.manager || f.manager,
      }))
      setPhase('fields')
      pushToast('Fields filled from document — review and submit')
    } catch (err) {
      pushToast(err instanceof Error ? err.message : 'Could not read document')
    } finally {
      setExtractBusy(false)
    }
  }

  function onDemoSelect(filename: OfferDemoFile | '') {
    setDemoFile(filename)
    if (!filename) return
    const demo = OFFER_DEMO_FILES.find((f) => f.filename === filename)
    if (demo) {
      setForm({
        legalName: demo.legalName,
        workEmail: demo.workEmail,
        workLocation: demo.workLocation,
        hireDate: demo.hireDate,
        monthlySalary: demo.monthlySalary != null ? String(demo.monthlySalary) : '',
        jobTitle: demo.jobTitle,
        manager: demo.manager,
      })
      setFileName(demo.filename)
    }
    void runExtract(filename)
  }

  async function onSubmit() {
    if (!form.legalName.trim()) {
      pushToast('Legal name is required')
      return
    }
    if (!form.hireDate) {
      pushToast('Joining date is required')
      return
    }
    const salaryNum = Number(String(form.monthlySalary).replace(/,/g, ''))
    if (!form.monthlySalary.trim() || !Number.isFinite(salaryNum) || salaryNum <= 0) {
      pushToast('Monthly salary is required')
      return
    }

    setSubmitBusy(true)
    setPhase('processing')
    setActiveStep(0)

    try {
      const preview = await clarityApi.previewInput(
        {
          kind: 'employee',
          name: form.legalName.trim(),
          country: form.workLocation,
          hireDate: form.hireDate,
          baseSalary: salaryNum,
          monthlyNet: salaryNum,
          manager: form.manager.trim() || undefined,
        },
        asOf,
      )
      setConfirmMsg(preview.confirmationMessage?.replace(/\*\*/g, '') || null)

      // Animate journey: Received → Read → Mapped (4s) → Validated → Cycle → Stored
      setActiveStep(0)
      await sleep(400)
      setActiveStep(1)
      await sleep(500)
      setActiveStep(2) // Mapped — hold 4 seconds with loader
      await sleep(4000)
      setActiveStep(3)
      await sleep(500)
      setActiveStep(4)
      await sleep(400)
      setActiveStep(5)

      let employee = await createEmployee({
        name: form.legalName.trim(),
        workEmail: form.workEmail.trim() || undefined,
        country: form.workLocation,
        hireDate: form.hireDate,
        monthlyNet: salaryNum,
        baseSalary: salaryNum,
        jobTitle: form.jobTitle.trim() || undefined,
        manager: form.manager.trim() || undefined,
        asOf,
      })
      setCreatedId(employee.id)

      if (demoFile || fileName) {
        const fixture = demoFile || fileName!
        try {
          employee = await attachDocument(employee.id, { fixture, asOf })
        } catch {
          /* attach optional if fixture unknown */
        }
      }

      const miss = [...(employee.missingFields || [])]
      setMissing(miss)
      setMissingValues({})
      if (miss.length) {
        setPhase('missing')
      } else {
        setPhase('done')
        pushToast(`${employee.name} saved`)
        navigate(`/people/${employee.id}`)
      }
    } catch (err) {
      pushToast(err instanceof Error ? err.message : 'Could not save employee')
      setPhase('fields')
    } finally {
      setSubmitBusy(false)
    }
  }

  async function saveMissing() {
    if (!createdId) return
    const payload: Record<string, string> = {}
    for (const f of missing) {
      const v = (missingValues[f] || '').trim()
      if (v) payload[f] = v
    }
    if (!Object.keys(payload).length) {
      pushToast('Enter at least one missing field, or skip to profile')
      return
    }
    setSubmitBusy(true)
    try {
      await fillMissingFields(createdId, { fields: payload, asOf })
      pushToast('Details saved')
      navigate(`/people/${createdId}`)
    } catch (err) {
      pushToast(err instanceof Error ? err.message : 'Could not save details')
    } finally {
      setSubmitBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PeopleTabs />
      <PageHeader title="Add employee" subtitle="HR tool · Employees" />

      {/* Step 1 — input source */}
      <section className="mb-4 rounded border border-border bg-surface p-4">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
          1 · Input from
        </p>
        <div className="grid grid-cols-3 gap-2">
          {(
            [
              { id: 'upload' as const, label: 'Upload', hint: 'From computer' },
              { id: 'gdrive' as const, label: 'Google Drive', hint: googleReady ? 'Picker' : 'Not set up' },
              { id: 'demo' as const, label: 'Demo', hint: 'Preset offer letter' },
            ] as const
          ).map((opt) => {
            const selected = source === opt.id
            const disabled = opt.id === 'gdrive' && !googleReady
            return (
              <button
                key={opt.id}
                type="button"
                data-testid={`input-source-${opt.id}`}
                disabled={disabled}
                onClick={() => pickSource(opt.id)}
                className={[
                  'rounded border px-3 py-3 text-left text-[13px] transition',
                  selected
                    ? 'border-text-primary bg-surface-recessed'
                    : 'border-border bg-surface hover:bg-surface-recessed',
                  disabled ? 'cursor-not-allowed opacity-50' : '',
                ].join(' ')}
              >
                <span className="font-medium text-text-primary">{opt.label}</span>
                <span className="mt-0.5 block text-[11px] text-text-muted">{opt.hint}</span>
              </button>
            )
          })}
        </div>
        {source === 'gdrive' && !googleReady ? (
          <p className="mt-2 text-xs text-text-muted">Google Drive not set up – see README</p>
        ) : null}
      </section>

      {/* Step 2 — select document */}
      {source && phase !== 'processing' && phase !== 'missing' && phase !== 'done' ? (
        <section className="mb-4 rounded border border-border bg-surface p-4">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
            2 · Select document
          </p>
          <p className="mb-3 text-xs text-text-secondary">
            We&apos;ll read name, job title, start date and salary, then fill the form.
          </p>

          {source === 'demo' ? (
            <label className="flex flex-col gap-1 text-xs text-text-secondary">
              Demo file
              <select
                className={inputClass}
                value={demoFile}
                disabled={extractBusy}
                aria-label="Demo file"
                onChange={(e) => onDemoSelect(e.target.value as OfferDemoFile | '')}
              >
                <option value="">Choose demo preset…</option>
                {OFFER_DEMO_FILES.map((f) => (
                  <option key={f.filename} value={f.filename}>
                    {f.filename}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {source === 'upload' ? (
            <label className="inline-flex h-9 cursor-pointer items-center rounded border border-border bg-surface px-3 text-xs hover:bg-surface-recessed">
              {extractBusy ? 'Reading…' : 'Upload from computer'}
              <input
                type="file"
                accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf"
                className="hidden"
                disabled={extractBusy}
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void runExtract(f.name, f)
                  e.target.value = ''
                }}
              />
            </label>
          ) : null}

          {source === 'gdrive' && googleReady ? (
            <Button
              variant="secondary"
              disabled={extractBusy}
              onClick={() =>
                pushToast('Google Picker – sign in, then pick a PDF from HR Documents')
              }
            >
              Choose from Google Drive
            </Button>
          ) : null}

          {fileName ? (
            <div className="mt-3 flex items-center justify-between rounded border border-border bg-canvas px-3 py-2 text-[13px]">
              <span className="flex items-center gap-2 text-text-primary">
                <FileText size={14} className="text-text-muted" />
                {fileName}
              </span>
              <StatusChip tone="ok">Ready</StatusChip>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* Step 3 — fields (auto-filled + editable) */}
      {(phase === 'fields' || (source && fileName && phase === 'source')) &&
      phase !== 'processing' &&
      phase !== 'missing' ? (
        <section className="mb-4 space-y-3 rounded border border-border bg-surface p-4">
          <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
            3 · Review details
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Legal name">
              <input
                aria-label="Legal name"
                className={inputClass}
                value={form.legalName}
                onChange={(e) => setForm((f) => ({ ...f, legalName: e.target.value }))}
              />
            </Field>
            <Field label="Work email">
              <input
                aria-label="Work email"
                type="email"
                className={inputClass}
                value={form.workEmail}
                onChange={(e) => setForm((f) => ({ ...f, workEmail: e.target.value }))}
              />
            </Field>
            <Field label="Work location">
              <select
                aria-label="Work location"
                className={inputClass}
                value={form.workLocation}
                onChange={(e) =>
                  setForm((f) => ({ ...f, workLocation: e.target.value as Country }))
                }
              >
                <option value="India">India</option>
                <option value="UK">UK</option>
                <option value="Germany">Germany</option>
                <option value="Brazil">Brazil</option>
              </select>
            </Field>
            <Field label="Joining date">
              <input
                aria-label="Joining date"
                type="date"
                className={inputClass}
                value={form.hireDate}
                onChange={(e) => setForm((f) => ({ ...f, hireDate: e.target.value }))}
              />
            </Field>
            <Field label="Monthly salary">
              <input
                aria-label="Monthly salary"
                className={inputClass}
                value={form.monthlySalary}
                onChange={(e) => setForm((f) => ({ ...f, monthlySalary: e.target.value }))}
              />
            </Field>
            <Field label="Job title">
              <input
                aria-label="Job title"
                className={inputClass}
                value={form.jobTitle}
                onChange={(e) => setForm((f) => ({ ...f, jobTitle: e.target.value }))}
              />
            </Field>
            <Field label="Manager">
              <input
                aria-label="Manager"
                className={inputClass}
                value={form.manager}
                onChange={(e) => setForm((f) => ({ ...f, manager: e.target.value }))}
              />
            </Field>
          </div>
          <p className="text-[11px] text-text-muted">
            Mid-month joiners are prorated. Date added will be {formatIsoDate(asOf)}.
          </p>
          <div className="flex justify-end border-t border-border pt-3">
            <Button
              type="button"
              variant="primary"
              disabled={submitBusy || extractBusy || !form.legalName.trim()}
              onClick={() => void onSubmit()}
            >
              Submit
            </Button>
          </div>
        </section>
      ) : null}

      {/* Processing journey */}
      {phase === 'processing' ? (
        <section className="mb-4 rounded border border-border bg-surface p-4">
          <p className="mb-3 text-[11px] font-medium uppercase tracking-wide text-text-muted">
            Multiplier data journey
          </p>
          {confirmMsg ? (
            <p className="mb-3 text-xs text-text-secondary">{confirmMsg}</p>
          ) : null}
          <ol className="space-y-2">
            {JOURNEY.map((step, i) => {
              const done = i < activeStep
              const current = i === activeStep
              const mappedWait = current && step.key === 'mapped'
              return (
                <li
                  key={step.key}
                  className={[
                    'flex items-center gap-2 rounded border px-3 py-2 text-[13px]',
                    current
                      ? 'border-text-primary bg-surface-recessed'
                      : done
                        ? 'border-border bg-canvas text-text-secondary'
                        : 'border-border text-text-muted',
                  ].join(' ')}
                >
                  {done ? (
                    <Check size={14} className="text-status-ok-text" />
                  ) : mappedWait ? (
                    <Loader2 size={14} className="animate-spin text-text-primary" />
                  ) : current ? (
                    <Loader2 size={14} className="animate-spin text-text-primary" />
                  ) : (
                    <span className="inline-block h-3.5 w-3.5 rounded-full border border-border" />
                  )}
                  <span className="font-medium">{step.label}</span>
                  {mappedWait ? (
                    <span className="ml-auto text-[11px] text-text-muted">Mapping fields…</span>
                  ) : null}
                </li>
              )
            })}
          </ol>
        </section>
      ) : null}

      {/* Missing fields */}
      {phase === 'missing' ? (
        <section className="mb-4 rounded border border-border bg-surface p-4">
          <ol className="mb-4 flex flex-wrap gap-2 border-b border-border pb-3">
            {JOURNEY.map((step) => (
              <li
                key={step.key}
                className="inline-flex items-center gap-1 rounded bg-canvas px-2 py-1 text-[11px] text-text-secondary"
              >
                <Check size={12} className="text-status-ok-text" />
                {step.label}
              </li>
            ))}
          </ol>
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-text-muted">
            Missing details
          </p>
          <p className="mb-3 text-xs text-text-secondary">
            Employee saved. Add the fields below so they can be paid, or open the profile and finish later.
          </p>
          <div className="space-y-2">
            {missing.map((field) => (
              <Field key={field} label={field}>
                <input
                  className={`${inputClass} border-status-danger-border`}
                  placeholder={`Add ${field}`}
                  value={missingValues[field] || ''}
                  onChange={(e) =>
                    setMissingValues((v) => ({ ...v, [field]: e.target.value }))
                  }
                />
              </Field>
            ))}
          </div>
          <div className="mt-4 flex justify-end gap-2 border-t border-border pt-3">
            <Button
              variant="secondary"
              disabled={submitBusy}
              onClick={() => createdId && navigate(`/people/${createdId}`)}
            >
              Skip for now
            </Button>
            <Button
              variant="primary"
              disabled={submitBusy}
              onClick={() => void saveMissing()}
            >
              {submitBusy ? 'Saving…' : 'Save details'}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  )
}

const inputClass =
  'h-8 w-full rounded border border-border bg-surface px-2 text-[13px] text-text-primary focus:border-text-primary focus:outline-none'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-text-secondary">
      {label}
      {children}
    </label>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components'
import { MultiplierLogo } from '@/components/MultiplierLogo'
import { clarityApi } from '@/api/clarityClient'
import { useAppStore } from '@/store'

const BRAND = '#863bff'

export function EmployeeFormPage() {
  const { token } = useParams<{ token: string }>()
  const asOf = useAppStore((s) => s.asOf)
  const pushToast = useAppStore((s) => s.pushToast)
  const refreshAll = useAppStore((s) => s.refreshAll)
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [fields, setFields] = useState<string[]>([])
  const [demo, setDemo] = useState<Record<string, string>>({})
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!token) return
    setError(null)
    void clarityApi
      .getForm(token, asOf)
      .then((res) => {
        setName(res.employee.name)
        setFields(res.fields)
        setDemo(res.demoValues)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'This form link is invalid or expired')
      })
  }, [token, asOf])

  async function submit() {
    if (!token) return
    setBusy(true)
    try {
      const res = await clarityApi.submitForm(token, values, asOf)
      pushToast(res.message)
      setDone(true)
      await refreshAll()
      navigate('/payroll/actions')
    } catch (err) {
      pushToast(err instanceof Error ? err.message : 'Could not submit')
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <div className="min-h-full bg-[#f0ebf8]">
        <div className="mx-auto max-w-[640px] py-10">
          <div className="rounded-lg border-t-8 bg-white p-8 shadow-sm" style={{ borderTopColor: BRAND }}>
            <h1 className="text-2xl font-normal text-text-primary">Form unavailable</h1>
            <p className="mt-2 text-sm text-text-secondary">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-full bg-[#f0ebf8]">
      <div className="mx-auto max-w-[640px] py-10">
        <div className="rounded-lg border-t-8 bg-white p-8 shadow-sm" style={{ borderTopColor: BRAND }}>
          <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: BRAND }}>
            <MultiplierLogo size={16} />
            <span>Powered by Multiplier</span>
          </div>
          <h1 className="mt-3 text-2xl font-normal text-text-primary">
            Payroll details for Acme Tech
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            {name ? `${name.split(' ')[0]}, add the fields below so we can pay you.` : 'Loading…'}
          </p>
          <p className="mt-2 text-xs text-text-muted">Please submit by the cycle deadline. This link is single-use.</p>
        </div>
        {fields.map((field) => (
          <div key={field} className="mt-3 rounded-lg bg-white p-6 shadow-sm">
            <label className="block text-sm font-medium text-text-primary">{field}</label>
            <input
              className="mt-2 w-full border-b border-border py-2 text-sm focus:outline-none"
              style={{ ['--tw-ring-color' as string]: BRAND }}
              value={values[field] ?? ''}
              onChange={(e) => setValues((s) => ({ ...s, [field]: e.target.value }))}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = BRAND
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = ''
              }}
              placeholder={demo[field] || field}
              disabled={done}
            />
            {demo[field] ? (
              <button
                type="button"
                className="mt-2 text-xs hover:underline"
                style={{ color: BRAND }}
                onClick={() => setValues((s) => ({ ...s, [field]: demo[field] }))}
              >
                Use demo value
              </button>
            ) : null}
          </div>
        ))}
        <div className="mt-4 flex justify-end">
          <Button
            variant="primary"
            disabled={busy || done || fields.some((f) => !(values[f] || '').trim())}
            onClick={() => void submit()}
          >
            Submit
          </Button>
        </div>
      </div>
    </div>
  )
}

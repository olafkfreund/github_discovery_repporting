import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { Customer } from '../../types'

const STORAGE_KEY = 'bps:settings:selected_customer_id'

export default function CustomerPicker() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [searchParams, setSearchParams] = useSearchParams()

  // On mount, load customers and restore or default the selection
  useEffect(() => {
    let cancelled = false

    api.listCustomers().then((data) => {
      if (cancelled) return
      setCustomers(data)
      setLoading(false)

      if (data.length === 0) return

      const stored = localStorage.getItem(STORAGE_KEY)
      const current = searchParams.get('customer_id')

      // Validate stored/current value against the fetched list
      const validIds = new Set(data.map((c) => c.id))
      const resolved =
        (current && validIds.has(current) ? current : null) ??
        (stored && validIds.has(stored) ? stored : null) ??
        data[0].id

      // Persist the resolved value
      localStorage.setItem(STORAGE_KEY, resolved)

      if (resolved !== current) {
        setSearchParams(
          (prev) => {
            prev.set('customer_id', resolved)
            return prev
          },
          { replace: true },
        )
      }
    })

    return () => {
      cancelled = true
    }
    // Run only on mount — intentionally not depending on searchParams
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value
    localStorage.setItem(STORAGE_KEY, id)
    setSearchParams(
      (prev) => {
        prev.set('customer_id', id)
        return prev
      },
      { replace: true },
    )
  }

  const selectedId = searchParams.get('customer_id') ?? ''

  return (
    <div className="flex items-center gap-2 px-6 py-3 bg-white border-b border-gray-200 sticky top-0 z-10">
      <label
        htmlFor="customer-picker"
        className="text-sm font-medium text-gray-700 whitespace-nowrap"
      >
        Customer:
      </label>
      {loading ? (
        <span className="text-sm text-gray-400">Loading…</span>
      ) : (
        <select
          id="customer-picker"
          value={selectedId}
          onChange={handleChange}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm
                     focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

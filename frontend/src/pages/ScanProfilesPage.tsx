import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type {
  Customer,
  ScanProfile,
  ScanProfileConfig,
  CategoryConfig,
  CategoryRegistryInfo,
} from '../types'

// ── Profile editor ───────────────────────────────────────────────────────────

interface ProfileEditorProps {
  registry: CategoryRegistryInfo[]
  initial?: ScanProfile
  onSave: (name: string, description: string, config: ScanProfileConfig) => Promise<void>
  onCancel: () => void
}

function ProfileEditor({ registry, initial, onSave, onCancel }: ProfileEditorProps) {
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [config, setConfig] = useState<ScanProfileConfig>(initial?.config ?? {})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())

  const getCatConfig = (cat: string): CategoryConfig => config.categories?.[cat] ?? {}

  const setCatConfig = (cat: string, update: Partial<CategoryConfig>) => {
    setConfig((prev) => ({
      ...prev,
      categories: {
        ...(prev.categories ?? {}),
        [cat]: { ...getCatConfig(cat), ...update },
      },
    }))
  }

  const toggleCategory = (cat: string) => {
    const current = getCatConfig(cat).enabled !== false
    setCatConfig(cat, { enabled: !current })
  }

  const setCatWeight = (cat: string, weight: number) => {
    setCatConfig(cat, { weight })
  }

  const toggleCheck = (cat: string, checkId: string) => {
    const catCfg = getCatConfig(cat)
    const checks = catCfg.checks ?? {}
    const current = checks[checkId]?.enabled !== false
    setCatConfig(cat, {
      checks: { ...checks, [checkId]: { ...checks[checkId], enabled: !current } },
    })
  }

  const setThreshold = (cat: string, checkId: string, key: string, value: number) => {
    const catCfg = getCatConfig(cat)
    const checks = catCfg.checks ?? {}
    const checkCfg = checks[checkId] ?? {}
    setCatConfig(cat, {
      checks: {
        ...checks,
        [checkId]: {
          ...checkCfg,
          thresholds: { ...(checkCfg.thresholds ?? {}), [key]: value },
        },
      },
    })
  }

  const toggleExpanded = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  // Calculate total weight for enabled categories
  const enabledCats = registry.filter((c) => getCatConfig(c.category).enabled !== false)
  const totalWeight = enabledCats.reduce(
    (sum, c) => sum + (getCatConfig(c.category).weight ?? c.weight),
    0
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Profile name is required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(name.trim(), description.trim(), config)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">
        {initial ? 'Edit Profile' : 'Create Profile'}
      </h3>
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">{error}</div>
      )}
      <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-6">
        {/* Name + Description */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Profile Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Strict Security Profile"
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm
                         focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Weight summary */}
        <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-md text-sm">
          <span className="text-gray-600">
            Enabled categories: <strong>{enabledCats.length}</strong> / {registry.length}
          </span>
          <span className="text-gray-400">|</span>
          <span className={`${Math.abs(totalWeight - 1.0) > 0.01 ? 'text-amber-600 font-medium' : 'text-gray-600'}`}>
            Total weight: {totalWeight.toFixed(2)}
            {Math.abs(totalWeight - 1.0) > 0.01 && ' (will be renormalised at scan time)'}
          </span>
        </div>

        {/* Category sections */}
        <div className="space-y-2">
          {registry.map((cat) => {
            const catCfg = getCatConfig(cat.category)
            const enabled = catCfg.enabled !== false
            const expanded = expandedCats.has(cat.category)

            return (
              <div key={cat.category} className={`border rounded-lg ${enabled ? 'border-gray-200' : 'border-gray-100 opacity-60'}`}>
                {/* Category header */}
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={() => toggleCategory(cat.category)}
                      className="rounded border-gray-300 text-indigo-600
                                 focus:ring-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => toggleExpanded(cat.category)}
                      className="flex items-center gap-2 text-sm font-medium text-gray-800 hover:text-indigo-600"
                    >
                      <svg
                        className={`h-4 w-4 transition-transform ${expanded ? 'rotate-90' : ''}`}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                      {cat.display_name}
                    </button>
                    <span className="text-xs text-gray-400">({cat.scope} · {cat.checks.length} checks)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-gray-500">Weight:</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      value={catCfg.weight ?? cat.weight}
                      onChange={(e) => setCatWeight(cat.category, parseFloat(e.target.value) || 0)}
                      disabled={!enabled}
                      className="w-20 rounded-md border border-gray-300 px-2 py-1 text-sm text-right
                                 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                                 disabled:bg-gray-100 disabled:text-gray-400"
                    />
                  </div>
                </div>

                {/* Checks list */}
                {expanded && enabled && (
                  <div className="border-t border-gray-100 px-4 py-3">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase">
                          <th className="pb-2 pr-3 w-8"></th>
                          <th className="pb-2 pr-3">Check</th>
                          <th className="pb-2 pr-3">Severity</th>
                          <th className="pb-2 pr-3">Weight</th>
                          <th className="pb-2">Thresholds</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {cat.checks.map((check) => {
                          const checkCfg = catCfg.checks?.[check.check_id] ?? {}
                          const checkEnabled = checkCfg.enabled !== false

                          return (
                            <tr key={check.check_id} className={checkEnabled ? '' : 'opacity-50'}>
                              <td className="py-2 pr-3">
                                <input
                                  type="checkbox"
                                  checked={checkEnabled}
                                  onChange={() => toggleCheck(cat.category, check.check_id)}
                                  className="rounded border-gray-300 text-indigo-600
                                             focus:ring-indigo-500"
                                />
                              </td>
                              <td className="py-2 pr-3">
                                <div className="font-medium text-gray-800">{check.check_id}</div>
                                <div className="text-xs text-gray-500">{check.check_name}</div>
                              </td>
                              <td className="py-2 pr-3">
                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                  check.severity === 'critical' ? 'bg-red-100 text-red-800' :
                                  check.severity === 'high' ? 'bg-orange-100 text-orange-800' :
                                  check.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                                  'bg-gray-100 text-gray-700'
                                }`}>
                                  {check.severity}
                                </span>
                              </td>
                              <td className="py-2 pr-3 text-gray-600">{check.weight}</td>
                              <td className="py-2">
                                {check.thresholds.length > 0 ? (
                                  <div className="flex flex-wrap gap-2">
                                    {check.thresholds.map((t) => (
                                      <div key={t.key} className="flex items-center gap-1">
                                        <label className="text-xs text-gray-500 whitespace-nowrap">{t.key}:</label>
                                        <input
                                          type="number"
                                          step="any"
                                          value={checkCfg.thresholds?.[t.key] ?? t.default_value}
                                          onChange={(e) =>
                                            setThreshold(
                                              cat.category,
                                              check.check_id,
                                              t.key,
                                              parseFloat(e.target.value) || 0
                                            )
                                          }
                                          disabled={!checkEnabled}
                                          className="w-20 rounded border border-gray-300 px-1.5 py-0.5 text-xs text-right
                                                     focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                                                     disabled:bg-gray-100"
                                        />
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-xs text-gray-400">-</span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md
                       hover:bg-indigo-700 disabled:opacity-50
                       focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            {saving ? 'Saving...' : initial ? 'Update Profile' : 'Create Profile'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md
                       border border-gray-300 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function ScanProfilesPage() {
  const { id: customerId } = useParams<{ id: string }>()
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [profiles, setProfiles] = useState<ScanProfile[]>([])
  const [registry, setRegistry] = useState<CategoryRegistryInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showEditor, setShowEditor] = useState(false)
  const [editingProfile, setEditingProfile] = useState<ScanProfile | undefined>()
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    if (!customerId) return
    setLoading(true)
    setError(null)
    try {
      const [cust, profileList, reg] = await Promise.all([
        api.getCustomer(customerId),
        api.listScanProfiles(customerId),
        api.getScannerRegistry(),
      ])
      setCustomer(cust)
      setProfiles(profileList)
      setRegistry(reg)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const handleCreate = async (name: string, description: string, config: ScanProfileConfig) => {
    if (!customerId) return
    const created = await api.createScanProfile(customerId, {
      name,
      description: description || undefined,
      config,
    })
    setProfiles((prev) => [created, ...prev])
    setShowEditor(false)
  }

  const handleUpdate = async (name: string, description: string, config: ScanProfileConfig) => {
    if (!editingProfile) return
    const updated = await api.updateScanProfile(editingProfile.id, {
      name,
      description: description || undefined,
      config,
    })
    setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
    setEditingProfile(undefined)
    setShowEditor(false)
  }

  const handleDelete = async (profileId: string) => {
    if (!window.confirm('Delete this scan profile?')) return
    setDeletingId(profileId)
    try {
      await api.deleteScanProfile(profileId)
      setProfiles((prev) => prev.filter((p) => p.id !== profileId))
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete profile')
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    )
  }

  if (error || !customer) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700 font-medium">Error loading data</p>
        <p className="text-red-600 text-sm mt-1">{error ?? 'Customer not found'}</p>
        <Link to="/customers" className="mt-3 inline-block text-red-700 underline text-sm">
          Back to Customers
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm">
        <Link to="/customers" className="text-indigo-600 hover:text-indigo-700">Customers</Link>
        <span className="mx-2 text-gray-400">/</span>
        <Link to={`/customers/${customer.id}`} className="text-indigo-600 hover:text-indigo-700">{customer.name}</Link>
        <span className="mx-2 text-gray-400">/</span>
        <span className="text-gray-700 font-medium">Scan Profiles</span>
      </nav>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Scan Profiles</h2>
          <p className="text-sm text-gray-500 mt-1">
            Configure which categories, checks, and thresholds apply when scanning {customer.name}.
          </p>
        </div>
        {!showEditor && (
          <button
            onClick={() => { setEditingProfile(undefined); setShowEditor(true) }}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm
                       font-medium rounded-md hover:bg-indigo-700"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Profile
          </button>
        )}
      </div>

      {/* Editor */}
      {showEditor && (
        <ProfileEditor
          registry={registry}
          initial={editingProfile}
          onSave={editingProfile ? handleUpdate : handleCreate}
          onCancel={() => { setShowEditor(false); setEditingProfile(undefined) }}
        />
      )}

      {/* Profile list */}
      {profiles.length === 0 && !showEditor ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">No scan profiles yet. Create one to customise scanning.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {profiles.map((profile) => {
            const catCount = Object.keys(profile.config.categories ?? {}).length
            const disabledCount = Object.values(profile.config.categories ?? {}).filter(
              (c) => c.enabled === false
            ).length

            return (
              <div
                key={profile.id}
                className="bg-white rounded-lg shadow p-5 flex items-center justify-between"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-gray-900">{profile.name}</h4>
                    {profile.is_default && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
                        Default
                      </span>
                    )}
                  </div>
                  {profile.description && (
                    <p className="text-xs text-gray-500 mt-1">{profile.description}</p>
                  )}
                  <p className="text-xs text-gray-400 mt-1">
                    {catCount > 0
                      ? `${catCount} categories configured, ${disabledCount} disabled`
                      : 'All defaults (no overrides)'}
                    {' · '}Created {new Date(profile.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => { setEditingProfile(profile); setShowEditor(true) }}
                    className="px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50
                               border border-indigo-200 rounded-md hover:bg-indigo-100"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => { void handleDelete(profile.id) }}
                    disabled={deletingId === profile.id}
                    className="px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50
                               border border-red-200 rounded-md hover:bg-red-100
                               disabled:opacity-50"
                  >
                    {deletingId === profile.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

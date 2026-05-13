import { useSearchParams } from 'react-router-dom'

export const SETTINGS_CUSTOMER_STORAGE_KEY = 'bps:settings:selected_customer_id'

// Reads the active customer for Settings pages. Prefers the URL param so
// deep-linked URLs win; falls back to localStorage so returning visitors
// don't see a "Select a customer" flash before CustomerPicker has finished
// hydrating the URL after its async customer-list fetch.
export function useSettingsCustomerId(): string {
  const [searchParams] = useSearchParams()
  const fromUrl = searchParams.get('customer_id')
  if (fromUrl) return fromUrl
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(SETTINGS_CUSTOMER_STORAGE_KEY) ?? ''
}

export interface Customer {
  id: string
  name: string
  slug: string
  contact_email: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface Connection {
  id: string
  customer_id: string
  platform: 'github' | 'gitlab' | 'azure_devops'
  display_name: string
  base_url: string | null
  auth_type: string
  org_or_group: string
  is_active: boolean
  last_validated_at: string | null
  created_at: string
  updated_at: string
}

export interface Scan {
  id: string
  customer_id: string
  connection_id: string
  status: 'pending' | 'scanning' | 'analyzing' | 'generating_report' | 'completed' | 'failed'
  started_at: string | null
  completed_at: string | null
  total_repos: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ScanScore {
  id: string
  scan_id: string
  category: string
  score: number
  max_score: number
  weight: number
  finding_count: number
  pass_count: number
  fail_count: number
}

export interface Finding {
  id: string
  scan_id: string
  scan_repo_id: string
  category: string
  check_id: string
  check_name: string
  severity: string
  status: string
  detail: string | null
  evidence: Record<string, unknown> | null
  weight: number
  score: number
}

export interface Report {
  id: string
  scan_id: string
  customer_id: string
  title: string
  generated_at: string
  overall_score: number | null
  dora_level: string | null
  pdf_path: string | null
  status: 'pending' | 'generating' | 'completed' | 'failed'
  created_at: string
  updated_at: string
}

export interface DashboardStats {
  total_customers: number
  total_scans: number
  total_reports: number
  recent_scan_count: number
}

export interface ConnectionCreatePayload {
  platform: 'github' | 'gitlab' | 'azure_devops'
  display_name: string
  org_or_group: string
  auth_type: 'token' | 'oauth' | 'pat'
  credentials: string
  base_url?: string
}

export interface ConnectionUpdatePayload {
  display_name?: string
  org_or_group?: string
  auth_type?: 'token' | 'oauth' | 'pat'
  credentials?: string
  base_url?: string | null
}

export interface CustomerCreatePayload {
  name: string
  contact_email?: string
  notes?: string
}

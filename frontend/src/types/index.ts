export interface AssetItem {
  id: string
  normalized_url: string
  title?: string | null
  status_code?: number | null
  screenshot_status: string
  label_status: string
  verified?: boolean
  source?: string | null
  first_seen_at?: string | null
  last_seen_at?: string | null
  screenshot_url?: string | null
  has_screenshot?: boolean
}

export interface SystemConfig {
  sample_mode: boolean
  screenshot_output_dir: string
  result_output_dir: string
  database_url: string
}

export interface SelectionItem {
  id: string
  selection_name: string
  selection_type: string
  created_by: string
}

export interface ReportCreatePayload {
  report_name: string
  scope_type: string
  selection_id?: string | null
  asset_ids?: string[]
  report_formats?: string[]
  exclude_false_positive?: boolean
  exclude_confirmed?: boolean
}

export interface ReportCreateResult {
  report_id: string
  status: string
}

export interface JobCreatePayload {
  job_name: string
  sources: string[]
  queries: Array<Record<string, unknown>>
  time_window?: Record<string, unknown> | null
  file_path?: string | null
  dedup_strategy?: string
  field_mapping?: Record<string, string>
  auto_verify?: boolean
  created_by?: string
}

export interface FofaCsvImportPayload {
  job_name: string
  file_path: string
  created_by?: string
}

export interface JobCreateResult {
  job_id: string
  status: string
  imported?: number
}

export interface LogItem {
  timestamp: string
  level: string
  source: 'task' | 'service'
  message: string
}

export interface LogsResponse {
  items: LogItem[]
  next_since?: string | null
}

export interface VerifyAssetsResult {
  updated: number
  verified: boolean
  success: number
  failed: number
}

export interface VerifyTaskStartResult {
  task_id: string
  status: string
}

export interface TaskProgress {
  task_id: string
  task_type: 'asset_verify' | 'asset_screenshot'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  total: number
  processed: number
  success: number
  failed: number
  message?: string | null
}

export interface CollectJob {
  id: string
  job_name: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  sources: string[] | Record<string, unknown>
  query_payload: Record<string, unknown>
  progress: number
  success_count: number
  failed_count: number
  duplicate_count: number
  total_count: number
  dedup_strategy: string
  field_mapping: Record<string, string>
  auto_verify: boolean
  created_at?: string
  finished_at?: string | null
  error_message?: string | null
}

export interface SelectionCreatePayload {
  selection_name: string
  selection_type: string
  filter_snapshot?: Record<string, unknown> | null
  asset_ids?: string[]
}

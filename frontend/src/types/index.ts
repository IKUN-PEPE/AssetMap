export interface AssetItem {
  id: string
  normalized_url: string
  domain?: string | null
  title?: string | null
  status_code?: number | null
  screenshot_status: string
  label_status: string
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
}

export interface JobCreateResult {
  job_id: string
  status: string
  imported?: number
}

export interface SelectionCreatePayload {
  selection_name: string
  selection_type: string
  filter_snapshot?: Record<string, unknown> | null
  asset_ids?: string[]
}

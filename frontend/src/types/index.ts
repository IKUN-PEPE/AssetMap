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
  verify_error?: string | null
  screenshot_error?: string | null
}

export type CollectJobStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled'
  | 'partial_success'

export interface SystemConfigItem {
  id: string
  config_key: string
  config_value: string
  config_group: string
  is_sensitive: boolean
  updated_at: string
}

export type SystemConfigValue = string | number | boolean | null | undefined

export type SystemConfigMap = Record<string, SystemConfigValue>

export type SystemConfig = SystemConfigMap

export interface SystemMessageResponse {
  message: string
}

export interface SystemConnectionTestPayload {
  platform: string
  config: Record<string, unknown>
}

export interface SystemConnectionTestResult {
  success: boolean
  platform: string
  error?: string
}

export interface SelectionItem {
  id: string
  selection_name: string
  selection_type: string
  created_by: string
}

export type ReportStatus = 'pending' | 'running' | 'completed' | 'failed' | 'file_missing'

export interface ReportRead {
  id: string
  report_name: string
  status: ReportStatus
  report_type?: string | null
  object_path?: string | null
  file_size?: number | null
  file_missing?: boolean
  download_url?: string | null
  created_at?: string | null
  finished_at?: string | null
  total_assets?: number
  excluded_assets?: number
  error_message?: string | null
}

export interface ReportCreatePayload {
  report_name: string
  scope_type: string
  selection_id?: string | null
  asset_ids?: string[]
  report_formats?: string[]
  report_content?: string | null
  file_name?: string | null
  total_assets?: number
  excluded_assets?: number
  exclude_false_positive?: boolean
  exclude_confirmed?: boolean
}

export interface ReportCreateResult {
  report_id: string
  status: string
}

export interface StatsOverview {
  total: number
  month_new: number
  today: number
  rate: number
  critical: number
}

export interface StatsDistributionItem {
  name: string
  value: number
}

export interface StatsDistributionResponse {
  sources: StatsDistributionItem[]
  verify: StatsDistributionItem[]
}

export interface StatsTrendsResponse {
  dates: string[]
  data: number[]
}

export interface CsvPreviewResponse {
  headers: string[]
  rows: Array<Record<string, string>>
  file_path: string
  detected_source_type?: string | null
}

export type JobTaskStageState = 'disabled' | 'pending' | 'running' | 'success' | 'failed' | 'partial_failed'

export interface JobTaskStage {
  state: JobTaskStageState
  started: boolean
  finished: boolean
  success: number
  failed: number
  last_error?: string | null
}

export interface JobTaskDetails {
  collection: {
    status: CollectJobStatus
    progress: number
    observation_count: number
    result_asset_count: number
  }
  post_process: {
    enabled: boolean
    state: JobTaskStageState
    verify: JobTaskStage
    screenshot: JobTaskStage
  }
}

export interface JobCreatePayload {
  job_name: string
  sources: string[]
  queries: Array<Record<string, unknown>>
  time_window?: Record<string, unknown> | null
  file_path?: string | null
  source_type?: string | null
  dedup_strategy?: string
  field_mapping?: Record<string, string>
  auto_verify?: boolean
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

export type JobLogState =
  | 'not_started'
  | 'running'
  | 'finished'
  | 'log_not_found'
  | 'log_empty'
  | 'log_ready'

export interface JobLogResponse {
  job_id: string
  log_state: JobLogState
  content: string
  exists: boolean
  started_at?: string | null
  finished_at?: string | null
  task_details?: JobTaskDetails
}

export interface JobResultPreviewItem {
  id: string
  source?: string | null
  normalized_url: string
  url?: string | null
  domain?: string | null
  ip?: string | null
  port?: number | null
  title?: string | null
  status_code?: number | null
  verified?: boolean | null
  screenshot_status?: string | null
  verify_error?: string | null
  screenshot_error?: string | null
}

export interface JobResultPreviewResponse {
  job_id: string
  items: JobResultPreviewItem[]
  total: number
  skip: number
  limit: number
  task_details?: JobTaskDetails
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
  status: CollectJobStatus
  sources: string[] | Record<string, unknown>
  query_payload: {
    queries?: Array<{ source?: string; query?: string } & Record<string, unknown>>
    time_window?: Record<string, unknown> | null
    file_path?: string | null
    source_type?: string | null
    [key: string]: unknown
  }
  progress: number
  success_count: number
  failed_count: number
  duplicate_count: number
  total_count: number
  dedup_strategy: string
  field_mapping: Record<string, string>
  auto_verify: boolean
  created_at?: string
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface CollectJobDetail extends CollectJob {
  duration?: number | null
  command_line?: string | null
  task_details?: JobTaskDetails
}

export interface SelectionCreatePayload {
  selection_name: string
  selection_type: string
  filter_snapshot?: Record<string, unknown> | null
  asset_ids?: string[]
}

import http from '@/api/http'
import type {
  CollectJob,
  CollectJobDetail,
  CsvPreviewResponse,
  JobCreatePayload,
  JobCreateResult,
  JobBatchOperationResponse,
  JobConfirmImportResponse,
  JobDiscardImportResponse,
  JobLogResponse,
  JobPendingAssetListResponse,
  JobResultPreviewResponse,
  TaskProgress,
  CollectJobStatus,
} from '@/types'

export async function listJobs() {
  const { data } = await http.get<CollectJob[]>('/api/v1/jobs/')
  return data
}

export async function fetchJobDetails(id: string): Promise<CollectJobDetail> {
  const { data } = await http.get<CollectJobDetail>(`/api/v1/jobs/${id}`)
  return data
}

export async function fetchJobLogs(id: string): Promise<JobLogResponse> {
  const { data } = await http.get<JobLogResponse>(`/api/v1/jobs/${id}/logs`)
  return data
}

export async function fetchJobResults(id: string, skip = 0, limit = 50): Promise<JobResultPreviewResponse> {
  const { data } = await http.get<JobResultPreviewResponse>(`/api/v1/jobs/${id}/results`, {
    params: { skip, limit },
  })
  return data
}

export async function fetchPendingJobAssets(id: string, skip = 0, limit = 50): Promise<JobPendingAssetListResponse> {
  const { data } = await http.get<JobPendingAssetListResponse>(`/api/v1/jobs/${id}/pending-assets`, {
    params: { skip, limit },
  })
  return data
}

export async function rerunJob(id: string): Promise<JobCreateResult> {
  const { data } = await http.post<JobCreateResult>(`/api/v1/jobs/${id}/rerun`)
  return data
}

export async function confirmJobImport(id: string, payload: { ids?: string[]; import_all: boolean }) {
  const { data } = await http.post<JobConfirmImportResponse>(`/api/v1/jobs/${id}/confirm-import`, payload)
  return data
}

export async function discardJobImport(id: string) {
  const { data } = await http.post<JobDiscardImportResponse>(`/api/v1/jobs/${id}/discard-import`)
  return data
}

export async function startTask(id: string) {
  const { data } = await http.post<{ message: string; job_id: string }>(`/api/v1/jobs/${id}/start`)
  return data
}

export async function stopTask(id: string) {
  const { data } = await http.post<{ message: string; job_id: string }>(`/api/v1/jobs/${id}/stop`)
  return data
}

export async function getTaskStatus(id: string) {
  const { data } = await http.get<{
    id: string
    status: CollectJobStatus
    progress: number
    success_count: number
    failed_count: number
    duplicate_count: number
    total_count: number
    started_at?: string
    finished_at?: string
    error_message?: string
  }>(`/api/v1/jobs/${id}/status`)
  return data
}

export async function previewCsv(formData: FormData) {
  const { data } = await http.post<CsvPreviewResponse>('/api/v1/jobs/preview', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return data
}

export async function createCollectJob(payload: JobCreatePayload) {
  const { data } = await http.post<JobCreateResult>('/api/v1/jobs/collect', payload)
  return data
}

export async function batchDeleteJobs(ids: string[]) {
  const { data } = await http.post<JobBatchOperationResponse>('/api/v1/jobs/batch-delete', { ids })
  return data
}

export async function batchRerunJobs(ids: string[]) {
  const { data } = await http.post<JobBatchOperationResponse>('/api/v1/jobs/batch-rerun', { ids })
  return data
}

export async function batchStartJobs(ids: string[]) {
  const { data } = await http.post<JobBatchOperationResponse>('/api/v1/jobs/batch-start', { ids })
  return data
}

export async function fetchVerifyTask(taskId: string) {
  const { data } = await http.get<TaskProgress>(`/api/v1/assets/verify-batch/${taskId}`)
  return data
}

export async function cancelVerifyTask(taskId: string) {
  const { data } = await http.post<TaskProgress>(`/api/v1/assets/verify-batch/${taskId}/cancel`)
  return data
}

export async function fetchScreenshotTask(taskId: string) {
  const { data } = await http.get<TaskProgress>(`/api/v1/screenshots/batch/${taskId}`)
  return data
}

export async function cancelScreenshotTask(taskId: string) {
  const { data } = await http.post<TaskProgress>(`/api/v1/screenshots/batch/${taskId}/cancel`)
  return data
}

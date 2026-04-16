import http from '@/api/http'
import type { 
  CollectJob, 
  FofaCsvImportPayload, 
  JobCreatePayload, 
  JobCreateResult, 
  TaskProgress 
} from '@/types'

export async function listJobs() {
  const { data } = await http.get<CollectJob[]>('/api/v1/jobs/')
  return data
}

export async function getCollectJob(id: string) {
  const { data } = await http.get<CollectJob>(`/api/v1/jobs/${id}`)
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
    status: string
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
  const { data } = await http.post<{
    headers: string[]
    rows: Array<Record<string, string>>
    file_path: string
  }>('/api/v1/jobs/preview', formData, {
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

export async function importFofaCsv(payload: FofaCsvImportPayload) {
  const { data } = await http.post<JobCreateResult>('/api/v1/jobs/import-fofa-csv', payload)
  return data
}

export async function uploadFofaCsv(formData: FormData) {
  const { data } = await http.post<JobCreateResult>('/api/v1/jobs/upload-fofa-csv', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return data
}

export async function uploadHunterCsv(formData: FormData) {
  const { data } = await http.post<JobCreateResult>('/api/v1/jobs/upload-hunter-csv', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
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

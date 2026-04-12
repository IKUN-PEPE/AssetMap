import http from '@/api/http'
import type { JobCreatePayload, JobCreateResult } from '@/types'

export async function createCollectJob(payload: JobCreatePayload) {
  const { data } = await http.post<JobCreateResult>('/api/v1/jobs/collect', payload)
  return data
}

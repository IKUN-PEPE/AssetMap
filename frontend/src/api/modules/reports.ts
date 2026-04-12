import http from '@/api/http'
import type { ReportCreatePayload, ReportCreateResult } from '@/types'

export async function createReport(payload: ReportCreatePayload) {
  const { data } = await http.post<ReportCreateResult>('/api/v1/reports', payload)
  return data
}

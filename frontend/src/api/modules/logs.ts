import http from '@/api/http'
import type { LogsResponse } from '@/types'

export async function fetchRecentLogs(params?: {
  source?: 'task' | 'service' | 'all'
  limit?: number
  since?: string
}) {
  const { data } = await http.get<LogsResponse>('/api/v1/logs/recent', { params })
  return data
}

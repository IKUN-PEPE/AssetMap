import http from '@/api/http'
import type { SystemConfig } from '@/types'

export async function fetchSystemConfig() {
  const { data } = await http.get<SystemConfig>('/api/v1/system/config')
  return data
}

export async function fetchHealth() {
  const { data } = await http.get('/health')
  return data
}

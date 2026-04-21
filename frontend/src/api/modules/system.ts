import http from '@/api/http'
import type {
  SystemConfig,
  SystemConfigItem,
  SystemConnectionTestPayload,
  SystemConnectionTestResult,
  SystemMessageResponse,
} from '@/types'

export async function listSystemConfigs(revealSensitive = false): Promise<SystemConfigItem[]> {
  const { data } = await http.get<SystemConfigItem[]>('/api/v1/system/', {
    params: revealSensitive ? { reveal_sensitive: true } : undefined,
  })
  return data
}

export async function updateSystemConfigs(payload: SystemConfig): Promise<SystemMessageResponse> {
  const { data } = await http.put<SystemMessageResponse>('/api/v1/system/', payload)
  return data
}

export async function testSystemConnection(payload: SystemConnectionTestPayload): Promise<SystemConnectionTestResult> {
  const { data } = await http.post<SystemConnectionTestResult>('/api/v1/system/test-connection', payload)
  return data
}

export async function initSystemConfigs(): Promise<SystemMessageResponse> {
  const { data } = await http.post<SystemMessageResponse>('/api/v1/system/init')
  return data
}

import http from '@/api/http'
import type { AssetItem, VerifyTaskStartResult } from '@/types'

export async function fetchAssets(params?: {
  q?: string
  source?: string
  label_status?: string
  screenshot_status?: string
  has_screenshot?: boolean
}) {
  const { data } = await http.get<AssetItem[]>('/api/v1/assets', { params })
  return data
}

export async function fetchAssetDetail(id: string) {
  const { data } = await http.get<AssetItem>(`/api/v1/assets/${id}`)
  return data
}

export async function batchLabel(asset_ids: string[], label_type: string) {
  const { data } = await http.post('/api/v1/labels/batch', { asset_ids, label_type })
  return data
}

export async function verifyAssets(asset_ids: string[]) {
  const { data } = await http.post<VerifyTaskStartResult>('/api/v1/assets/verify-batch', { asset_ids, verified: true })
  return data
}

export async function deleteAsset(id: string) {
  const { data } = await http.delete(`/api/v1/assets/${id}`)
  return data
}

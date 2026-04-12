import http from '@/api/http'
import type { AssetItem } from '@/types'

export async function fetchAssets() {
  const { data } = await http.get<AssetItem[]>('/api/v1/assets')
  return data
}

export async function fetchAssetDetail(id: string) {
  const { data } = await http.get<AssetItem>(`/api/v1/assets/${id}`)
  return data
}

export async function batchScreenshot(asset_ids: string[]) {
  const { data } = await http.post('/api/v1/screenshots/batch', { asset_ids })
  return data
}

export async function batchLabel(asset_ids: string[], label_type: string) {
  const { data } = await http.post('/api/v1/labels/batch', { asset_ids, label_type })
  return data
}

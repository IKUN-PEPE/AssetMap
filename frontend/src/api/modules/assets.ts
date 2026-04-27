import http from '@/api/http';
import type { AssetItem, VerifyTaskStartResult } from '@/types';

interface FetchAssetsParams {
  q?: string;
  source?: string;
  label_status?: string;
  screenshot_status?: string;
  has_screenshot?: boolean;
  month_new?: boolean;
}

export function fetchAssets(params: FetchAssetsParams): Promise<AssetItem[]> {
  return http.get('/api/v1/assets/', { params }).then(res => res.data);
}

export function fetchAssetDetail(id: string): Promise<AssetItem> {
  return http.get(`/api/v1/assets/${id}`).then(res => res.data);
}

export function deleteAsset(id: string): Promise<void> {
  return http.delete(`/api/v1/assets/${id}`).then(res => res.data);
}

export function verifyAssets(asset_ids: string[]): Promise<VerifyTaskStartResult> {
  return http.post('/api/v1/assets/verify-batch', { asset_ids }).then(res => res.data);
}

export function batchLabel(asset_ids: string[], label_type: string): Promise<any> {
  return http.post('/api/v1/labels/batch', { asset_ids, label_type }).then(res => res.data);
}

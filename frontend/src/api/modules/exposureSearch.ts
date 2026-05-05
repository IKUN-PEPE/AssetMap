import http from '../http'
import type { ExposureSearchTask } from '@/types'

export const createExposureSearchTask = (data: any) => {
  return http.post('/api/v1/exposure-search/tasks', data)
}

export const listExposureSearchTasks = () => {
  return http.get<ExposureSearchTask[]>('/api/v1/exposure-search/tasks')
}

export const getExposureSearchTask = (taskId: string) => {
  return http.get<ExposureSearchTask>(`/api/v1/exposure-search/tasks/${taskId}`)
}

export const listExposureSearchResults = (taskId: string, params?: any) => {
  return http.get(`/api/v1/exposure-search/tasks/${taskId}/results`, { params })
}

export const batchUpdateExposureResults = (data: { ids: string[]; status: string }) => {
  return http.post('/api/v1/exposure-search/results/batch-update', data)
}

export const batchDeleteExposureResults = (data: { ids: string[] }) => {
  return http.post('/api/v1/exposure-search/results/batch-delete', data)
}

export const confirmImportExposureResults = (taskId: string, data: { ids?: string[]; import_all_valid?: boolean }) => {
  return http.post(`/api/v1/exposure-search/tasks/${taskId}/confirm-import`, data)
}

export const deleteExposureSearchTask = (taskId: string) => {
  return http.delete(`/api/v1/exposure-search/tasks/${taskId}`)
}

export const batchDeleteExposureSearchTasks = (data: { ids: string[] }) => {
  return http.post('/api/v1/exposure-search/tasks/batch-delete', data)
}

export const stopExposureSearchTask = (taskId: string) => {
  return http.post(`/api/v1/exposure-search/tasks/${taskId}/stop`)
}

export const retryExposureSearchQuery = (taskId: string, query: string) => {
  return http.post(`/api/v1/exposure-search/tasks/${taskId}/retry-query`, { query })
}

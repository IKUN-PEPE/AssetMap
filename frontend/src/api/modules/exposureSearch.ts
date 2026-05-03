import http from '../http'

export const createExposureSearchTask = (data: any) => {
  return http.post('/api/v1/exposure-search/tasks', data)
}

export const listExposureSearchTasks = () => {
  return http.get('/api/v1/exposure-search/tasks')
}

export const getExposureSearchTask = (taskId: string) => {
  return http.get(`/api/v1/exposure-search/tasks/${taskId}`)
}

export const listExposureSearchResults = (taskId: string, params?: any) => {
  return http.get(`/api/v1/exposure-search/tasks/${taskId}/results`, { params })
}

export const batchUpdateExposureResults = (data: { ids: string[]; status: string }) => {
  return http.post('/api/v1/exposure-search/results/batch-update', data)
}

export const confirmImportExposureResults = (taskId: string, data: { ids?: string[]; import_all_valid?: boolean }) => {
  return http.post(`/api/v1/exposure-search/tasks/${taskId}/confirm-import`, data)
}

export const deleteExposureSearchTask = (taskId: string) => {
  return http.delete(`/api/v1/exposure-search/tasks/${taskId}`)
}

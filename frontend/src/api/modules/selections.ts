import http from '@/api/http'
import type { SelectionCreatePayload, SelectionItem } from '@/types'

export async function fetchSelections() {
  const { data } = await http.get<SelectionItem[]>('/api/v1/selections')
  return data
}

export async function createSelection(payload: SelectionCreatePayload) {
  const { data } = await http.post('/api/v1/selections', payload)
  return data
}

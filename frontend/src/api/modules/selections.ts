import http from '@/api/http';
import type { SelectionCreatePayload } from '@/types';

interface SelectionItem {
  id: string
  selection_name: string
  selection_type: string
  created_by: string
}

export function fetchSelections(): Promise<SelectionItem[]> {
  return http.get('/api/v1/selections/').then(res => res.data);
}

export function createSelection(payload: SelectionCreatePayload): Promise<{ selection_id: string }> {
  return http.post('/api/v1/selections/', payload).then(res => res.data);
}

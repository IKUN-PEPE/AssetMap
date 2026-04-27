import http from '@/api/http'
import type { ReportCreatePayload, ReportRead } from '@/types'

export type DownloadReportResult = Blob & {
  fileName: string | null
}

function stripQuotes(value: string) {
  if (value.length >= 2 && value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1)
  }
  return value
}

function decodeHeaderFileName(value: string) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function parseContentDispositionFileName(header?: string | null) {
  if (!header) return null

  const filenameStarMatch = header.match(/filename\*\s*=\s*([^;]+)/i)
  if (filenameStarMatch) {
    const rawValue = stripQuotes(filenameStarMatch[1].trim())
    const encodedPart = rawValue.match(/^[^']*'[^']*'(.*)$/)?.[1] ?? rawValue
    const decodedValue = decodeHeaderFileName(encodedPart).trim()
    if (decodedValue) {
      return decodedValue
    }
  }

  const filenameMatch = header.match(/filename\s*=\s*("([^"]+)"|[^;]+)/i)
  if (filenameMatch) {
    const rawValue = stripQuotes(filenameMatch[1].trim()).trim()
    if (rawValue) {
      return rawValue
    }
  }

  return null
}

export async function createReport(payload: ReportCreatePayload) {
  const { data } = await http.post<ReportRead>('/api/v1/reports', payload)
  return data
}

export async function fetchReports() {
  const { data } = await http.get<ReportRead[]>('/api/v1/reports')
  return data
}

export async function regenerateReport(id: string) {
  const { data } = await http.post<ReportRead>(`/api/v1/reports/${id}/regenerate`)
  return data
}

export async function deleteReport(id: string) {
  const { data } = await http.delete<void>(`/api/v1/reports/${id}`)
  return data
}

export async function downloadReport(id: string): Promise<DownloadReportResult> {
  const response = await http.get<Blob>(`/api/v1/reports/${id}/download`, { responseType: 'blob' })
  const blob = response.data as DownloadReportResult
  blob.fileName = parseContentDispositionFileName(response.headers['content-disposition'])
  return blob
}

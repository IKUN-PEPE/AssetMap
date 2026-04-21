import http from '@/api/http'
import type {
  StatsDistributionResponse,
  StatsOverview,
  StatsTrendsResponse,
} from '@/types'

export async function fetchStatsOverview() {
  const { data } = await http.get<StatsOverview>('/api/v1/stats/overview')
  return data
}

export async function fetchStatsDistribution() {
  const { data } = await http.get<StatsDistributionResponse>('/api/v1/stats/distribution')
  return data
}

export async function fetchStatsTrends() {
  const { data } = await http.get<StatsTrendsResponse>('/api/v1/stats/trends')
  return data
}

import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { StatsResponse } from "@/types"

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: () => api.get<StatsResponse>("/api/stats"),
  })
}

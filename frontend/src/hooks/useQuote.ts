import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { CombinedQuoteResponse } from "@/types"

export function useCombinedQuote(ids: number[]) {
  const key = ids.join(",")
  return useQuery({
    queryKey: ["quote-combined", key],
    queryFn: () =>
      api.get<CombinedQuoteResponse>(`/api/quote/combined?ids=${key}`),
    enabled: ids.length > 0,
  })
}

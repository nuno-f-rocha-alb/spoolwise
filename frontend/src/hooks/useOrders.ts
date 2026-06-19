import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { OrdersResponse } from "@/types"

export function useOrders() {
  return useQuery({
    queryKey: ["orders"],
    queryFn: () => api.get<OrdersResponse>("/api/orders"),
  })
}

export function useDeleteOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      api.del<{ ok: boolean; stock_restored: boolean }>(`/api/orders/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
      qc.invalidateQueries({ queryKey: ["filaments"] })
    },
  })
}

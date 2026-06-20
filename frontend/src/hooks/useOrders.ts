import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type {
  AppSettings,
  OrderFormPayload,
  OrderMutationResult,
  OrdersResponse,
} from "@/types"

export function useOrders() {
  return useQuery({
    queryKey: ["orders"],
    queryFn: () => api.get<OrdersResponse>("/api/orders"),
  })
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<AppSettings>("/api/settings"),
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AppSettings) =>
      api.put<AppSettings>("/api/settings", payload),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data)
      // currency + retail mode are shown app-wide and bootstrap from /me
      qc.invalidateQueries({ queryKey: ["auth", "me"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
      qc.invalidateQueries({ queryKey: ["orders"] })
      qc.invalidateQueries({ queryKey: ["filaments"] })
    },
  })
}

function invalidateOrderData(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["orders"] })
  qc.invalidateQueries({ queryKey: ["dashboard"] })
  qc.invalidateQueries({ queryKey: ["filaments"] })
}

export function useCreateOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: OrderFormPayload) =>
      api.post<OrderMutationResult>("/api/orders", payload),
    onSuccess: () => invalidateOrderData(qc),
  })
}

export function useUpdateOrder(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: OrderFormPayload) =>
      api.put<OrderMutationResult>(`/api/orders/${id}`, payload),
    onSuccess: () => {
      invalidateOrderData(qc)
      qc.invalidateQueries({ queryKey: ["order", id] })
    },
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

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type {
  Filament,
  FilamentDetailResponse,
  FilamentsResponse,
} from "@/types"

export function useFilaments() {
  return useQuery({
    queryKey: ["filaments"],
    queryFn: () => api.get<FilamentsResponse>("/api/filaments"),
  })
}

export function useFilamentDetail(id: number) {
  return useQuery({
    queryKey: ["filament", id],
    queryFn: () => api.get<FilamentDetailResponse>(`/api/filaments/${id}`),
    enabled: Number.isFinite(id),
  })
}

export interface CreateFilamentInput {
  name: string
  material: string
  color: string
  color_hex?: string | null
  stock_g?: number
  price_per_kg?: number
}

export function useCreateFilament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateFilamentInput) =>
      api.post<{ filament: Filament }>("/api/filaments", input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filaments"] }),
  })
}

export function usePurchaseFilament(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { quantity_g: number; price_per_kg: number }) =>
      api.post<{ filament: Filament }>(`/api/filaments/${id}/purchase`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filaments"] })
      qc.invalidateQueries({ queryKey: ["filament", id] })
    },
  })
}

export function useEditPurchase(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { purchaseId: number; quantity_g: number; price_per_kg: number }) =>
      api.put<FilamentDetailResponse>(`/api/filaments/${id}/purchases/${input.purchaseId}`, {
        quantity_g: input.quantity_g,
        price_per_kg: input.price_per_kg,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filaments"] })
      qc.invalidateQueries({ queryKey: ["filament", id] })
    },
  })
}

export function useDeletePurchase(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (purchaseId: number) =>
      api.del<FilamentDetailResponse>(`/api/filaments/${id}/purchases/${purchaseId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filaments"] })
      qc.invalidateQueries({ queryKey: ["filament", id] })
    },
  })
}

export function useAdjustFilament(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { stock_g: number }) =>
      api.post<{ filament: Filament }>(`/api/filaments/${id}/adjust`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filaments"] })
      qc.invalidateQueries({ queryKey: ["filament", id] })
    },
  })
}

export function useDeleteFilament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del<{ ok: boolean }>(`/api/filaments/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filaments"] }),
  })
}

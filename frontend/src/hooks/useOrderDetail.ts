import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { OrderDetailResponse } from "@/types"

export function useOrderDetail(id: number) {
  return useQuery({
    queryKey: ["order", id],
    queryFn: () => api.get<OrderDetailResponse>(`/api/orders/${id}`),
    enabled: Number.isFinite(id),
  })
}

function useOrderMutation<TVars>(
  oid: number,
  fn: (vars: TVars) => Promise<unknown>,
  opts?: { invalidateStock?: boolean }
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["order", oid] })
      qc.invalidateQueries({ queryKey: ["orders"] })
      if (opts?.invalidateStock) {
        qc.invalidateQueries({ queryKey: ["filaments"] })
        qc.invalidateQueries({ queryKey: ["dashboard"] })
      }
    },
  })
}

export function useTogglePlatePrinted(oid: number) {
  return useOrderMutation(oid, (pid: number) =>
    api.post(`/api/orders/${oid}/plates/${pid}/toggle-printed`)
  )
}

export function useTogglePlateSkipped(oid: number) {
  return useOrderMutation(
    oid,
    (pid: number) => api.post(`/api/orders/${oid}/plates/${pid}/toggle-skipped`),
    { invalidateStock: true }
  )
}

export function useMarkPrinted(oid: number) {
  return useOrderMutation(oid, (value: boolean) =>
    api.post(`/api/orders/${oid}/printed`, { value })
  )
}

export function useMarkDelivered(oid: number) {
  return useOrderMutation(oid, (value: boolean) =>
    api.post(`/api/orders/${oid}/delivered`, { value })
  )
}

export function useUploadOrderFile(oid: number) {
  return useOrderMutation(oid, (file: File) => {
    const fd = new FormData()
    fd.append("file", file)
    return api.upload(`/api/orders/${oid}/files`, fd)
  })
}

export function useDeleteOrderFile(oid: number) {
  return useOrderMutation(oid, (fid: number) => api.del(`/api/files/${fid}`))
}

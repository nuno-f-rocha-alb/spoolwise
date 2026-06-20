import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { AdminUser, AdminUsersResponse } from "@/types"

export function useAdminUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => api.get<AdminUsersResponse>("/api/admin/users"),
  })
}

function useUsersMutation<TVars>(fn: (vars: TVars) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  })
}

export interface CreateUserPayload {
  username: string
  display_name?: string | null
  email?: string | null
  password?: string
  is_admin: boolean
}

export function useCreateUser() {
  return useUsersMutation((payload: CreateUserPayload) =>
    api.post<{ user: AdminUser }>("/api/admin/users", payload)
  )
}

export function useToggleUserActive() {
  return useUsersMutation((uid: number) =>
    api.post<{ user: AdminUser }>(`/api/admin/users/${uid}/toggle-active`)
  )
}

export function useResetUserPassword() {
  // No list change — doesn't need invalidation, but harmless and keeps one path.
  return useUsersMutation((vars: { uid: number; password: string }) =>
    api.post(`/api/admin/users/${vars.uid}/reset-password`, {
      password: vars.password,
    })
  )
}

export function useDeleteUser() {
  return useUsersMutation((uid: number) => api.del(`/api/admin/users/${uid}`))
}

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { api, ApiError } from "@/lib/api"
import type { AuthMe, LoginResponse } from "@/types"

async function fetchMe(): Promise<AuthMe | null> {
  try {
    return await api.get<AuthMe>("/api/auth/me")
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null
    throw err
  }
}

export function useAuthQuery() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: fetchMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}

export function useAuth() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useAuthQuery()

  const login = React.useCallback(
    async (username: string, password: string, remember: boolean) => {
      const res = await api.post<LoginResponse>("/api/auth/login", {
        username,
        password,
        remember,
      })
      queryClient.setQueryData<AuthMe>(["auth", "me"], {
        authenticated: true,
        ...res,
      })
      return res
    },
    [queryClient]
  )

  const logout = React.useCallback(async () => {
    try {
      await api.post("/api/auth/logout")
    } finally {
      queryClient.setQueryData(["auth", "me"], null)
      queryClient.clear()
    }
  }, [queryClient])

  return {
    me: data ?? null,
    user: data?.user ?? null,
    isAuthenticated: !!data?.authenticated,
    isLoading,
    isError,
    login,
    logout,
  }
}

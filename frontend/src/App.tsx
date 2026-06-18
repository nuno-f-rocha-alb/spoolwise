import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppLayout } from "@/components/AppLayout"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { ThemeProvider } from "@/hooks/useTheme"
import ComingSoon from "@/pages/ComingSoon"
import Dashboard from "@/pages/Dashboard"
import Filaments from "@/pages/Filaments"
import FilamentForm from "@/pages/FilamentForm"
import FilamentPurchase from "@/pages/FilamentPurchase"
import Login from "@/pages/Login"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/filaments" element={<Filaments />} />
                <Route path="/filaments/new" element={<FilamentForm />} />
                <Route
                  path="/filaments/:id/purchase"
                  element={<FilamentPurchase />}
                />
                <Route
                  path="/orders"
                  element={<ComingSoon title="Orders" />}
                />
                <Route
                  path="/orders/new"
                  element={<ComingSoon title="New order" />}
                />
                <Route
                  path="/orders/:id"
                  element={<ComingSoon title="Order detail" />}
                />
                <Route path="/stats" element={<ComingSoon title="Statistics" />} />
                <Route
                  path="/settings"
                  element={<ComingSoon title="Settings" />}
                />
                <Route
                  path="/admin/users"
                  element={<ComingSoon title="Manage users" />}
                />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

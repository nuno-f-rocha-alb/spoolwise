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
import Orders from "@/pages/Orders"
import OrderDetail from "@/pages/OrderDetail"
import OrderForm from "@/pages/OrderForm"
import Quote from "@/pages/Quote"
import QuoteCombined from "@/pages/QuoteCombined"
import Settings from "@/pages/Settings"

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
                <Route path="/orders" element={<Orders />} />
                <Route path="/orders/new" element={<OrderForm />} />
                <Route path="/orders/:id" element={<OrderDetail />} />
                <Route path="/orders/:id/edit" element={<OrderForm />} />
                <Route path="/stats" element={<ComingSoon title="Statistics" />} />
                <Route path="/settings" element={<Settings />} />
                <Route
                  path="/admin/users"
                  element={<ComingSoon title="Manage users" />}
                />
              </Route>
              {/* Standalone, print-friendly — outside the app shell (no nav). */}
              <Route path="/quote/combined" element={<QuoteCombined />} />
              <Route path="/quote/:id" element={<Quote />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

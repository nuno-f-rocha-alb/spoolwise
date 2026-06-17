import { LogOut } from "lucide-react"

import { Logo } from "@/components/Logo"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/hooks/useAuth"

// Placeholder landing — proves the auth/session/shell wiring. The full
// Dashboard page is migrated in a later increment.
export default function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-dvh bg-background">
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <div className="flex items-center gap-2">
          <Logo className="size-7" />
          <span className="font-semibold tracking-tight">Spoolwise</span>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <span
            className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
            aria-hidden
          >
            {user?.initials}
          </span>
          <Button variant="outline" size="sm" onClick={() => logout()}>
            <LogOut className="size-4" /> Sign out
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-16 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">
          Signed in as {user?.display_name || user?.username}
        </h1>
        <p className="mt-2 text-muted-foreground">
          The React SPA shell is live. Pages are being migrated one at a time —
          this landing is a placeholder for the Dashboard.
        </p>
      </main>
    </div>
  )
}

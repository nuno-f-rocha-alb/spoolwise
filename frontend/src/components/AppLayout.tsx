import { LogOut, Plus, Users } from "lucide-react"
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom"

import { Logo } from "@/components/Logo"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/filaments", label: "Filaments" },
  { to: "/orders", label: "Orders" },
  { to: "/stats", label: "Statistics" },
  { to: "/settings", label: "Settings" },
]

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-accent text-accent-foreground"
      : "text-muted-foreground hover:bg-muted hover:text-foreground"
  )
}

export function AppLayout() {
  const { me, user, logout } = useAuth()
  const navigate = useNavigate()

  const canSignOut = !me?.sso_session && !me?.disable_local_login

  async function handleSignOut() {
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2 font-semibold tracking-tight"
          >
            <Logo className="size-7" />
            <span className="hidden sm:inline">Spoolwise</span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <Button asChild size="sm" className="hidden sm:inline-flex">
              <Link to="/orders/new">
                <Plus className="size-4" /> New order
              </Link>
            </Button>
            <Button
              asChild
              size="sm"
              variant="outline"
              className="hidden lg:inline-flex"
            >
              <Link to="/filaments/new">
                <Plus className="size-4" /> Filament
              </Link>
            </Button>

            <ThemeToggle />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="flex items-center gap-2 rounded-full outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
                  aria-label="Account menu"
                >
                  <span
                    className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
                    aria-hidden
                  >
                    {user?.initials}
                  </span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-56">
                <DropdownMenuLabel className="flex flex-col gap-0.5">
                  <span className="font-semibold">
                    {user?.display_name || user?.username}
                  </span>
                  <span className="text-xs font-normal text-muted-foreground">
                    @{user?.username}
                  </span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {user?.is_admin && (
                  <DropdownMenuItem asChild>
                    <Link to="/admin/users">
                      <Users className="size-4" /> Manage users
                    </Link>
                  </DropdownMenuItem>
                )}
                {me?.sso_session ? (
                  <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                    Signed in via SSO. Sign out from your identity provider.
                  </DropdownMenuLabel>
                ) : (
                  canSignOut && (
                    <DropdownMenuItem variant="destructive" onSelect={handleSignOut}>
                      <LogOut className="size-4" /> Sign out
                    </DropdownMenuItem>
                  )
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* mobile nav row */}
        <nav className="flex gap-1 overflow-x-auto px-4 pb-2 md:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={navClass}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}

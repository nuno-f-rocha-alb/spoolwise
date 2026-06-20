import * as React from "react"
import { Plus, ShieldCheck, Trash2 } from "lucide-react"

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  styledCancel,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { useAuth } from "@/hooks/useAuth"
import {
  useAdminUsers,
  useCreateUser,
  useDeleteUser,
  useResetUserPassword,
  useToggleUserActive,
} from "@/hooks/useAdminUsers"
import { ApiError } from "@/lib/api"
import { formatDate, formatDateTime } from "@/lib/format"
import type { AdminUser } from "@/types"

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong."
}

export default function Users() {
  const { user: me } = useAuth()
  const { data, isLoading, isError } = useAdminUsers()
  const create = useCreateUser()
  const toggle = useToggleUserActive()
  const reset = useResetUserPassword()
  const del = useDeleteUser()

  const [createOpen, setCreateOpen] = React.useState(false)
  const [resetTarget, setResetTarget] = React.useState<AdminUser | null>(null)
  const [deleteTarget, setDeleteTarget] = React.useState<AdminUser | null>(null)
  const [rowError, setRowError] = React.useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner className="size-6 text-muted-foreground" />
      </div>
    )
  }
  if (isError || !data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Couldn’t load users</AlertTitle>
        <AlertDescription>You may not have admin access.</AlertDescription>
      </Alert>
    )
  }

  const { users, trust_proxy_auth: proxyAuth } = data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Manage users</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Create and administer accounts. All data is isolated per user.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" /> New user
        </Button>
      </div>

      {proxyAuth && (
        <Alert>
          <AlertTitle>Proxy-auth mode is active.</AlertTitle>
          <AlertDescription>
            Accounts are auto-created on first sign-in via the upstream identity
            provider. Use the form only to pre-create a user (e.g. to grant admin
            rights before their first login).
          </AlertDescription>
        </Alert>
      )}

      {rowError && (
        <Alert variant="destructive">
          <AlertDescription>{rowError}</AlertDescription>
        </Alert>
      )}

      <Card className="gap-0 overflow-hidden py-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                <th className="w-12 px-4 py-2.5" />
                <th className="px-4 py-2.5 text-left font-medium">Username</th>
                <th className="px-4 py-2.5 text-left font-medium">Email</th>
                <th className="px-4 py-2.5 text-left font-medium">Role</th>
                <th className="px-4 py-2.5 text-left font-medium">Status</th>
                <th className="px-4 py-2.5 text-left font-medium">Created</th>
                <th className="px-4 py-2.5 text-left font-medium">Last login</th>
                <th className="px-4 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-border/60">
                  <td className="px-4 py-2.5">
                    <span
                      className="flex size-9 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
                      aria-hidden
                    >
                      {u.initials}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="font-semibold">{u.username}</div>
                    {u.display_name && u.display_name !== u.username && (
                      <div className="text-xs text-muted-foreground">
                        {u.display_name}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {u.email || "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    {u.is_admin ? (
                      <Badge>Admin</Badge>
                    ) : (
                      <Badge variant="secondary">User</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {u.is_active ? (
                      <Badge variant="success">Active</Badge>
                    ) : (
                      <Badge variant="secondary">Inactive</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">
                    {u.created_at ? formatDate(u.created_at) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">
                    {u.last_login_at ? formatDateTime(u.last_login_at) : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setResetTarget(u)}
                      >
                        Reset password
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={u.id === me?.id || toggle.isPending}
                        onClick={() => {
                          setRowError(null)
                          toggle.mutate(u.id, {
                            onError: (e) => setRowError(errMsg(e)),
                          })
                        }}
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:bg-destructive/10"
                        disabled={u.id === me?.id}
                        aria-label={`Delete ${u.username}`}
                        onClick={() => {
                          setRowError(null)
                          setDeleteTarget(u)
                        }}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        proxyAuth={proxyAuth}
        pending={create.isPending}
        onSubmit={(payload, onErr) =>
          create.mutate(payload, {
            onSuccess: () => setCreateOpen(false),
            onError: (e) => onErr(errMsg(e)),
          })
        }
      />

      <ResetPasswordDialog
        target={resetTarget}
        onClose={() => setResetTarget(null)}
        pending={reset.isPending}
        onSubmit={(password, onErr) =>
          resetTarget &&
          reset.mutate(
            { uid: resetTarget.id, password },
            {
              onSuccess: () => setResetTarget(null),
              onError: (e) => onErr(errMsg(e)),
            }
          )
        }
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete user?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes <strong>{deleteTarget?.username}</strong>.
              This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className={styledCancel()}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={del.isPending}
              onClick={() =>
                deleteTarget &&
                del.mutate(deleteTarget.id, {
                  onSuccess: () => setDeleteTarget(null),
                  onError: (e) => {
                    setRowError(errMsg(e))
                    setDeleteTarget(null)
                  },
                })
              }
            >
              {del.isPending ? <Spinner /> : null}
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function CreateUserDialog({
  open,
  onOpenChange,
  proxyAuth,
  pending,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  proxyAuth: boolean
  pending: boolean
  onSubmit: (
    payload: {
      username: string
      display_name: string | null
      email: string | null
      password: string
      is_admin: boolean
    },
    onError: (msg: string) => void
  ) => void
}) {
  const [error, setError] = React.useState<string | null>(null)
  const [isAdmin, setIsAdmin] = React.useState(false)

  // Reset transient state whenever the dialog opens.
  React.useEffect(() => {
    if (open) {
      setError(null)
      setIsAdmin(false)
    }
  }, [open])

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    const fd = new FormData(e.currentTarget)
    const password = String(fd.get("password") || "")
    onSubmit(
      {
        username: String(fd.get("username") || "").trim(),
        display_name: String(fd.get("display_name") || "").trim() || null,
        email: String(fd.get("email") || "").trim() || null,
        ...(password && { password }),
        is_admin: isAdmin,
      },
      setError
    )
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <form onSubmit={handleSubmit}>
          <AlertDialogHeader>
            <AlertDialogTitle>New user</AlertDialogTitle>
          </AlertDialogHeader>
          <div className="space-y-3 py-4">
            <div className="space-y-1.5">
              <Label htmlFor="cu-username">Username</Label>
              <Input
                id="cu-username"
                name="username"
                autoComplete="username"
                autoCapitalize="off"
                spellCheck={false}
                required
              />
              <p className="text-xs text-muted-foreground">
                Used for sign-in. Must be unique.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cu-display">
                Display name{" "}
                <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input id="cu-display" name="display_name" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cu-email">
                Email <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input id="cu-email" name="email" type="email" autoComplete="email" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cu-password">
                Password
                {proxyAuth && (
                  <span className="text-muted-foreground">
                    {" "}
                    (optional in proxy-auth mode)
                  </span>
                )}
              </Label>
              <Input
                id="cu-password"
                name="password"
                type="password"
                autoComplete="new-password"
                required={!proxyAuth}
              />
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={isAdmin}
                onCheckedChange={(v) => setIsAdmin(v === true)}
              />
              <ShieldCheck className="size-4 text-muted-foreground" />
              Grant admin privileges
            </label>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel className={styledCancel()} type="button">
              Cancel
            </AlertDialogCancel>
            <Button type="submit" disabled={pending}>
              {pending ? <Spinner /> : null}
              Create user
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function ResetPasswordDialog({
  target,
  onClose,
  pending,
  onSubmit,
}: {
  target: AdminUser | null
  onClose: () => void
  pending: boolean
  onSubmit: (password: string, onError: (msg: string) => void) => void
}) {
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (target) setError(null)
  }, [target])

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    const fd = new FormData(e.currentTarget)
    onSubmit(String(fd.get("password") || ""), setError)
  }

  return (
    <AlertDialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <AlertDialogContent>
        <form onSubmit={handleSubmit}>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset password</AlertDialogTitle>
            <AlertDialogDescription>
              Setting a new password for <strong>{target?.username}</strong>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1.5 py-4">
            <Label htmlFor="rp-password">New password</Label>
            <Input
              id="rp-password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
            />
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel className={styledCancel()} type="button">
              Cancel
            </AlertDialogCancel>
            <Button type="submit" disabled={pending}>
              {pending ? <Spinner /> : null}
              Update password
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  )
}

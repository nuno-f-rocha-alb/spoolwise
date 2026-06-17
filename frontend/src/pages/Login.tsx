import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useNavigate, useLocation } from "react-router-dom"
import { AlertCircle, LogIn } from "lucide-react"

import { Logo } from "@/components/Logo"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { useAuth } from "@/hooks/useAuth"
import { ApiError } from "@/lib/api"

const schema = z.object({
  username: z.string().trim().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
  remember: z.boolean(),
})

type FormValues = z.infer<typeof schema>

export default function Login() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = React.useState<string | null>(null)

  const from =
    (location.state as { from?: string } | null)?.from ?? "/"

  React.useEffect(() => {
    if (isAuthenticated) navigate(from, { replace: true })
  }, [isAuthenticated, from, navigate])

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "", remember: false },
  })

  const remember = watch("remember")

  async function onSubmit(values: FormValues) {
    setFormError(null)
    try {
      await login(values.username, values.password, values.remember)
      navigate(from, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setFormError(
          "Local sign-in is disabled. Sign in through your identity provider."
        )
      } else if (err instanceof ApiError) {
        setFormError(err.message)
      } else {
        setFormError("Something went wrong. Please try again.")
      }
    }
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center bg-background px-6 py-12">
      {/* ambient brand glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div className="absolute -right-24 -top-24 size-[28rem] rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-32 -left-24 size-[26rem] rounded-full bg-filament/10 blur-3xl" />
      </div>

      <ThemeToggle className="absolute right-4 top-4 z-10" />

      <main className="relative z-10 w-full max-w-[420px]">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo className="size-12" />
          <h1 className="text-2xl font-semibold tracking-tight">Spoolwise</h1>
        </div>

        <div className="rounded-xl border border-border bg-card p-6 shadow-lg sm:p-8">
          <div className="mb-6 space-y-1">
            <h2 className="text-xl font-semibold tracking-tight">Sign in</h2>
            <p className="text-sm text-muted-foreground">
              Welcome back. Please enter your credentials.
            </p>
          </div>

          <div aria-live="polite" aria-atomic="true">
            {formError && (
              <Alert variant="destructive" className="mb-4">
                <AlertCircle />
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}
          </div>

          <form
            onSubmit={handleSubmit(onSubmit)}
            noValidate
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                autoCapitalize="off"
                spellCheck={false}
                autoFocus
                aria-invalid={!!errors.username}
                {...register("username")}
              />
              {errors.username && (
                <p className="text-xs text-destructive">
                  {errors.username.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!errors.password}
                {...register("password")}
              />
              {errors.password && (
                <p className="text-xs text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Checkbox
                id="remember"
                checked={remember}
                onCheckedChange={(v) => setValue("remember", v === true)}
              />
              <Label htmlFor="remember" className="font-normal">
                Remember me on this device
              </Label>
            </div>

            <Button
              type="submit"
              className="mt-2 w-full"
              size="lg"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <Spinner /> Signing in…
                </>
              ) : (
                <>
                  <LogIn className="size-4" /> Sign in
                </>
              )}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          Spoolwise · 3D print manager
        </p>
      </main>
    </div>
  )
}

import * as React from "react"
import { ArrowLeft, Printer } from "lucide-react"
import { Link } from "react-router-dom"

import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * Standalone, print-friendly wrapper for the customer-facing quote pages.
 * Rendered outside the app shell (no nav) — mirrors the standalone Jinja
 * quote.html / quote_combined.html. The action bar is hidden when printing.
 */
export function QuoteFrame({
  eyebrow,
  meta,
  backTo,
  backLabel,
  footerDate,
  width = "max-w-2xl",
  children,
}: {
  eyebrow: string
  meta: React.ReactNode
  backTo: string
  backLabel: string
  footerDate: string
  width?: string
  children: React.ReactNode
}) {
  return (
    <div className="min-h-dvh bg-muted/30 px-3 py-8 print:bg-white print:py-0">
      <div className={cn("mx-auto", width)}>
        <div className="mb-6 flex items-start justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {eyebrow}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">{meta}</div>
          </div>
          <div className="flex gap-2 print:hidden">
            <Button variant="outline" size="sm" onClick={() => window.print()}>
              <Printer className="size-4" /> Print
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link to={backTo}>
                <ArrowLeft className="size-4" /> {backLabel}
              </Link>
            </Button>
          </div>
        </div>

        {children}

        <div className="mt-10 flex items-center justify-center gap-1.5 border-t border-border pt-4 text-xs text-muted-foreground">
          <Logo className="size-3.5" /> Generated with Spoolwise · {footerDate}
        </div>
      </div>
    </div>
  )
}

/** Brand-gradient totals panel shared by both quote views. */
export function PriceBox({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="mb-6 rounded-xl p-6 text-white shadow-sm"
      style={{ background: "linear-gradient(135deg, #0d6efd 0%, #6610f2 100%)" }}
    >
      {children}
    </div>
  )
}

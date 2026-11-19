"use client";
import clsx from "clsx";
import { Loader2, X } from "lucide-react";
import { createContext, forwardRef, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { initials } from "@/lib/format";

/* ---------- buttons ---------- */
type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-accent text-accent-text hover:bg-accent-hover shadow-card",
  secondary: "bg-surface text-text border border-border hover:bg-surface-2 hover:border-border-strong shadow-card",
  ghost: "text-text-2 hover:text-text hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90 shadow-card",
};
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode;
}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
  return (
    <button ref={ref} disabled={disabled || loading}
      className={clsx("inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors select-none",
        "disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap",
        size === "sm" ? "h-7 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm", variants[variant], className)} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

/* ---------- form fields ---------- */
const field = "rounded-lg border border-border bg-surface px-3 text-sm text-text placeholder:text-text-3 " +
  "transition-colors hover:border-border-strong focus:border-accent focus:outline-none focus:ring-3 focus:ring-[var(--ring)]";
const width = (c?: string) => (/(^|\s)!?(w-|max-w-)/.test(c ?? "") ? "" : "w-full");
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={clsx(field, width(className), "h-9", className)} {...p} />;
});
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} className={clsx(field, width(className), "py-2 min-h-20 resize-y", className)} {...p} />;
});
export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx(field, width(className), "h-9 pr-8 appearance-none bg-[length:16px] bg-[right_8px_center] bg-no-repeat", className)}
    style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2371717a' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }} {...p}>{children}</select>;
}
/** A labelled field. `group` renders a plain container (role=group) for several controls with labels of their
 *  own (checkbox lists): a <label> must never contain other labels or it forwards clicks twice. */
export function Field({ label, hint, children, className, group }: { label: string; hint?: ReactNode; children: ReactNode; className?: string; group?: boolean }) {
  const inner = (<>
    <span className="block text-[13px] font-medium text-text">{label}</span>
    {children}
    {hint && <span className="block text-xs text-text-3">{hint}</span>}
  </>);
  return group ? <div role="group" aria-label={label} className={clsx("space-y-1.5", className)}>{inner}</div>
    : <label className={clsx("block space-y-1.5", className)}>{inner}</label>;
}

/* ---------- display ---------- */
type Tone = "neutral" | "accent" | "success" | "warning" | "danger";
const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text-2 border-border",
  accent: "bg-accent-soft text-accent border-transparent",
  success: "bg-success-soft text-success border-transparent",
  warning: "bg-warning-soft text-warning border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
};
export function Badge({ tone = "neutral", children, className, dot }: { tone?: Tone; children: ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", tones[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}{children}
    </span>
  );
}

export function Card({ children, className, ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("rounded-xl border border-border bg-surface shadow-card", className)} {...rest}>{children}</div>;
}

export function Progress({ value, tone = "accent", className }: { value: number; tone?: "accent" | "success" | "danger"; className?: string }) {
  const color = tone === "success" ? "bg-success" : tone === "danger" ? "bg-danger" : "bg-accent";
  return (
    <div className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-surface-2", className)} role="progressbar"
      aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className={clsx("h-full rounded-full transition-[width] duration-500", color)} style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  );
}

export function Avatar({ name, email, url, size = 28 }: { name: string; email?: string; url?: string | null; size?: number }) {
  const hue = [...(email || name)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 0);
  if (url) return <img src={url} alt="" className="rounded-full object-cover" style={{ width: size, height: size }} />;
  return (
    <span className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{ width: size, height: size, fontSize: size * 0.38, background: `hsl(${hue} 55% 50%)` }}>
      {initials(name, email)}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("size-4 animate-spin text-text-3", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton rounded-lg", className)} />;
}

export function Empty({ icon, title, body, action }: { icon: ReactNode; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong px-6 py-14 text-center">
      <div className="mb-3 flex size-11 items-center justify-center rounded-xl bg-surface-2 text-text-2">{icon}</div>
      <p className="font-medium text-text">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-text-2">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, breadcrumb }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; breadcrumb?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {breadcrumb && <div className="mb-1.5 flex items-center gap-1.5 text-[13px] text-text-3">{breadcrumb}</div>}
        <h1 className="truncate text-xl font-semibold tracking-tight text-text">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-text-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ---------- tabs ---------- */
export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[];
}) {
  return (
    <div className="mb-5 flex gap-1 border-b border-border" role="tablist">
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={clsx("-mb-px flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 pb-2.5 pt-1 text-sm font-medium transition-colors",
            value === it.value ? "border-accent text-text" : "border-transparent text-text-2 hover:text-text")}>
          {it.label}
          {it.count != null && <span className="rounded-md bg-surface-2 px-1.5 text-xs text-text-2 tabular">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------- dialog ---------- */
export function Dialog({ open, onClose, title, description, children, footer, width = 460 }: {
  open: boolean; onClose: () => void; title: string; description?: ReactNode; children: ReactNode; footer?: ReactNode; width?: number;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose(); }}
      className="m-auto w-[calc(100%-32px)] rounded-2xl border border-border bg-surface p-0 text-text shadow-pop" style={{ maxWidth: width }}>
      {open && (
        <div>
          <div className="flex items-start justify-between gap-4 px-5 pt-5">
            <div>
              <h2 className="text-base font-semibold">{title}</h2>
              {description && <p className="mt-1 text-sm text-text-2">{description}</p>}
            </div>
            <button onClick={onClose} className="rounded-md p-1 text-text-3 hover:bg-surface-2 hover:text-text" aria-label="Close"><X className="size-4" /></button>
          </div>
          <div className="space-y-4 px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-border bg-surface-2/50 px-5 py-3 rounded-b-2xl">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

/* ---------- toasts ---------- */
interface Toast { id: number; tone: "success" | "danger" | "neutral"; text: string }
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => undefined);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "neutral") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, tone, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={clsx("pointer-events-auto rounded-xl border bg-surface px-4 py-3 text-sm shadow-pop",
            t.tone === "danger" ? "border-danger/40" : t.tone === "success" ? "border-success/40" : "border-border")}>
            <span className={clsx("mr-2 inline-block size-2 rounded-full", t.tone === "danger" ? "bg-danger" : t.tone === "success" ? "bg-success" : "bg-accent")} />
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

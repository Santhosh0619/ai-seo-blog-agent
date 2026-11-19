import { Check, Laptop, Moon, Sparkles, Sun, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { PRODUCT } from "./brand";
import { useTheme } from "./state";

export function Logo({ to = "/", size = 30 }) {
  return (
    <Link className="logo" to={to}>
      <span className="logo-mark" style={{ width: size, height: size }}><Sparkles size={size * 0.56} strokeWidth={2.4} /></span>
      {PRODUCT}
    </Link>
  );
}

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const opts = [["system", Laptop, "System theme"], ["light", Sun, "Light theme"], ["dark", Moon, "Dark theme"]];
  return (
    <div className="seg" role="group" aria-label="Theme">
      {opts.map(([m, Icon, label]) => (
        <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)} aria-label={label} title={label} style={{ padding: "6px 9px" }}><Icon size={15} /></button>
      ))}
    </div>
  );
}

export function ScoreRing({ score, size = 84 }) {
  const [p, setP] = useState(0);
  useEffect(() => { const t = setTimeout(() => setP(score), 60); return () => clearTimeout(t); }, [score]);
  const cls = score >= 85 ? "" : score >= 60 ? "mid" : "low";
  return <div className={`ring ${cls}`} style={{ "--p": p, "--size": `${size}px` }} role="img" aria-label={`SEO score ${score} out of 100`}><b>{score}</b></div>;
}

export function Badge({ kind = "neutral", children, icon: Icon }) {
  return <span className={`badge ${kind}`}>{Icon && <Icon size={12} strokeWidth={2.6} />}{children}</span>;
}
export const Verified = () => <Badge kind="ok" icon={Check}>Verified</Badge>;
export const Estimate = () => <Badge kind="est" icon={Sparkles}>AI estimate</Badge>;

export function Modal({ title, children, onClose, actions }) {
  const ref = useRef();
  useEffect(() => {
    ref.current?.focus();
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <h3>{title}</h3>
        <div className="muted">{children}</div>
        <div className="actions">{actions}</div>
      </div>
    </div>
  );
}

export function Alert({ kind = "info", children, onClose }) {
  return (
    <div className={`alert ${kind}`} role={kind === "bad" ? "alert" : "status"}>
      <div style={{ flex: 1 }}>{children}</div>
      {onClose && <button className="icon-btn" style={{ width: 24, height: 24 }} onClick={onClose} aria-label="Dismiss"><X size={14} /></button>}
    </div>
  );
}

export const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.2 5.5-4.7 7.2l7.3 5.7c4.3-4 6.7-9.8 6.7-17.4z" />
    <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 010-9.4l-7.9-6.1a24 24 0 000 21.6l7.9-6.1z" />
    <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.3-5.7c-2 1.4-4.6 2.3-8.6 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
  </svg>
);

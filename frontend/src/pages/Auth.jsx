import { Eye, EyeOff, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth, useMeta } from "../state";
import { Alert, GoogleIcon, Logo, ThemeToggle } from "../ui";
import { DemoSteps } from "./Landing";

const GOOGLE_ERRORS = {
  google_cancelled: "Google sign-in was cancelled.", google_state: "That sign-in expired. Please try again.", google_failed: "Google sign-in failed. Please try again.",
  google_email: "Your Google email is not verified, so we could not use it.", google_off: "Google sign-in is not set up on this server yet.",
};

export default function Auth({ mode }) {
  const signup = mode === "signup";
  const { user, setUser } = useAuth();
  const meta = useMeta();
  const nav = useNavigate();
  const [q] = useSearchParams();
  const topic = q.get("topic") || "";
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(GOOGLE_ERRORS[q.get("error")] || "");
  if (user) return <Navigate to={`/app/new${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`} replace />;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const r = await api(`/api/auth/${signup ? "signup" : "login"}`, { method: "POST", body: form });
      setUser(r.user);
      nav(`/app/new${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`, { replace: true });
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };
  return (
    <div className="auth">
      <div className="auth-form fade-up">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><Logo /><ThemeToggle /></div>
        <h1 className="display">{signup ? "Create your account" : "Welcome back"}</h1>
        <p className="muted" style={{ marginBottom: 22 }}>{signup ? "Free to start. 2 blog pages a day, no card." : "Sign in to see your pages and create new ones."}</p>
        {topic && signup && <Alert kind="info">Your topic <b>“{topic}”</b> is saved. Sign up and we will start with it.</Alert>}
        {err && <Alert kind="bad" onClose={() => setErr("")}>{err}</Alert>}
        {meta.google && (<>
          <a className="gbtn" href="/api/auth/google/start"><GoogleIcon /> Continue with Google</a>
          <div className="or">or use your email</div>
        </>)}
        <form onSubmit={submit} noValidate>
          {signup && <div className="field"><label htmlFor="name">Name (optional)</label><input id="name" className="input" autoComplete="name" value={form.name} onChange={set("name")} maxLength={60} /></div>}
          <div className="field"><label htmlFor="email">Email</label><input id="email" className="input" type="email" autoComplete="email" required value={form.email} onChange={set("email")} placeholder="you@example.com" /></div>
          <div className="field">
            <label htmlFor="pw">Password</label>
            <div style={{ position: "relative" }}>
              <input id="pw" className="input" type={show ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} required minLength={8} value={form.password} onChange={set("password")} placeholder={signup ? "At least 8 characters" : "Your password"} style={{ paddingRight: 44 }} />
              <button type="button" className="icon-btn" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)} style={{ position: "absolute", right: 4, top: 4 }}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button>
            </div>
          </div>
          <button className="btn btn-primary btn-lg btn-block" disabled={busy || !form.email || form.password.length < 1}>{busy ? <Loader2 size={18} className="spin-i" style={{ animation: "spin 1s linear infinite" }} /> : null}{signup ? "Create account" : "Sign in"}</button>
        </form>
        {!signup && (
          <p className="hint" style={{ marginTop: 14 }}>
            Forgot your password? There is no email reset yet. {meta.google ? <>Use <b>Continue with Google</b> with the same email address and you will get into your existing account.</> : "Create a new account, or contact the site owner."}
          </p>
        )}
        <p className="muted" style={{ marginTop: 20, fontSize: 14 }}>
          {signup ? <>Already have an account? <Link to={`/login${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`}>Sign in</Link></> : <>New here? <Link to={`/signup${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`}>Create an account</Link></>}
        </p>
        {signup && <p className="hint" style={{ marginTop: 14 }}>We store your email, your pages and your run history. We never store your Gemini key. You can export or delete everything from your account page. <Link to="/privacy">Privacy</Link></p>}
      </div>
      <aside className="auth-art" aria-hidden="true">
        <div className="art-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700 }}><Sparkles size={18} /> One topic in, one SEO page out</div>
          <DemoSteps speed={1100} />
        </div>
      </aside>
    </div>
  );
}

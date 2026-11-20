import { CheckCircle2, Eye, EyeOff, Loader2, MailCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Alert, Logo, ThemeToggle } from "../ui";
import { DemoSteps } from "./Landing";

function Frame({ title, sub, children }) {
  return (
    <div className="auth">
      <div className="auth-form fade-up">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><Logo /><ThemeToggle /></div>
        <h1 className="display">{title}</h1>
        <p className="muted" style={{ marginBottom: 22 }}>{sub}</p>
        {children}
      </div>
      <aside className="auth-art" aria-hidden="true"><div className="art-card"><DemoSteps speed={1100} /></div></aside>
    </div>
  );
}

export function Forgot() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { await api("/api/auth/forgot", { method: "POST", body: { email } }); setSent(true); }
    catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };
  if (sent) {
    return (
      <Frame title="Check your email" sub="If an account exists for that address, we sent a link to reset the password.">
        <div className="alert ok"><MailCheck size={18} /><div>The link is valid for 30 minutes and works once. It can take a minute to arrive. Check your spam folder if you do not see it.</div></div>
        <Link className="btn btn-block" to="/login">Back to sign in</Link>
      </Frame>
    );
  }
  return (
    <Frame title="Forgot your password?" sub="Enter your email and we will send you a link to choose a new one.">
      {err && <Alert kind="bad" onClose={() => setErr("")}>{err}</Alert>}
      <form onSubmit={submit} noValidate>
        <div className="field"><label htmlFor="email">Email</label><input id="email" className="input" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></div>
        <button className="btn btn-primary btn-lg btn-block" disabled={busy || !email.includes("@")}>{busy && <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} />}Send reset link</button>
      </form>
      <p className="muted" style={{ marginTop: 20, fontSize: 14 }}>Signed up with Google? Go back and use <b>Continue with Google</b>. <Link to="/login">Back to sign in</Link></p>
    </Frame>
  );
}

export function ResetPassword() {
  const nav = useNavigate();
  // The token is in the #fragment of the emailed link, so it is never sent to (or logged by) the server.
  const token = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("t") || "";
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { await api("/api/auth/reset", { method: "POST", body: { token, password: pw } }); setDone(true); setTimeout(() => nav("/login", { replace: true }), 2500); }
    catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };
  if (!token) {
    return <Frame title="Reset link missing" sub="This page needs the link from your email."><Link className="btn btn-primary btn-block" to="/forgot">Request a new link</Link></Frame>;
  }
  if (done) {
    return <Frame title="Password changed" sub="You can now sign in with your new password."><div className="alert ok"><CheckCircle2 size={18} /><div>All other devices were signed out. Taking you to the sign-in page…</div></div><Link className="btn btn-primary btn-block" to="/login">Sign in</Link></Frame>;
  }
  return (
    <Frame title="Choose a new password" sub="Use at least 8 characters.">
      {err && <Alert kind="bad" onClose={() => setErr("")}>{err} {err.includes("expired") && <Link to="/forgot">Request a new link</Link>}</Alert>}
      <form onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="pw">New password</label>
          <div style={{ position: "relative" }}>
            <input id="pw" className="input" type={show ? "text" : "password"} autoComplete="new-password" required minLength={8} autoFocus value={pw} onChange={(e) => setPw(e.target.value)} style={{ paddingRight: 44 }} />
            <button type="button" className="icon-btn" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)} style={{ position: "absolute", right: 4, top: 4 }}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button>
          </div>
        </div>
        <button className="btn btn-primary btn-lg btn-block" disabled={busy || pw.length < 8}>{busy && <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} />}Change password</button>
      </form>
    </Frame>
  );
}

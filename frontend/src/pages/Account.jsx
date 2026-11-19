import { Download, LogOut, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PRODUCT } from "../brand";
import { useAuth, useToast } from "../state";
import { Modal, ThemeToggle } from "../ui";

export default function Account() {
  const { user, logout, setUser } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const [ask, setAsk] = useState(false);
  const [typed, setTyped] = useState("");
  const remove = async () => {
    try { await api("/api/account", { method: "DELETE" }); setUser(null); toast("Your account and data were deleted"); nav("/"); } catch (e) { toast(e.message); }
  };
  return (
    <div style={{ maxWidth: 720 }}>
      <div className="page-head"><div><h1 className="display">Account</h1><p>Your details and your data.</p></div></div>
      <div className="card card-pad" style={{ marginBottom: 18 }}>
        <h3 style={{ marginBottom: 12 }}>Profile</h3>
        <div className="grid2" style={{ margin: 0, gap: 14 }}>
          <div><div className="label">Name</div>{user.name || "Not set"}</div><div><div className="label">Email</div>{user.email}</div>
          <div><div className="label">Sign-in method</div>{[user.has_password && "Email and password", user.google && "Google"].filter(Boolean).join(" and ")}</div>
          <div><div className="label">Theme</div><div style={{ marginTop: 4 }}><ThemeToggle /></div></div>
        </div>
        <div style={{ marginTop: 18 }}><button className="btn" onClick={async () => { await logout(); nav("/"); }}><LogOut size={16} /> Sign out</button></div>
      </div>

      <div className="card card-pad" style={{ marginBottom: 18 }}>
        <h3 style={{ marginBottom: 8 }}><ShieldCheck size={18} style={{ verticalAlign: -3, color: "var(--ok)" }} /> Your data</h3>
        <p className="muted">{PRODUCT} stores your email, the pages you create (text, images and the research behind them) and a short run history. It never stores your Gemini key. Pages are private unless you turn on a share link. Free Gemini keys may let Google use prompts to improve its products, so do not put private information in your topic or notes.</p>
        <div style={{ marginTop: 16 }}><a className="btn" href="/api/account/export" download><Download size={16} /> Download all my data</a></div>
      </div>

      <div className="card card-pad" style={{ borderColor: "color-mix(in srgb, var(--bad) 30%, var(--line))" }}>
        <h3 style={{ marginBottom: 8, color: "var(--bad)" }}>Delete account</h3>
        <p className="muted">Permanently deletes your account, every page, image and share link. This cannot be undone.</p>
        <div style={{ marginTop: 16 }}><button className="btn btn-danger" onClick={() => setAsk(true)}><Trash2 size={16} /> Delete my account</button></div>
      </div>

      {ask && <Modal title="Delete your account?" onClose={() => setAsk(false)} actions={<><button className="btn" onClick={() => setAsk(false)}>Cancel</button><button className="btn btn-danger" disabled={typed !== "DELETE"} onClick={remove}>Delete everything</button></>}>
        <p>Type <b>DELETE</b> to confirm.</p><input className="input" style={{ marginTop: 12 }} value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Type DELETE to confirm" autoFocus /></Modal>}
    </div>
  );
}

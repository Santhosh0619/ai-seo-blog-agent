import { ChevronDown, FilePlus2, History as HistoryIcon, LogOut, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../state";
import { Logo, ThemeToggle } from "../ui";

const LINKS = [["/app/new", FilePlus2, "New blog"], ["/app/history", HistoryIcon, "My pages"], ["/app/account", Settings, "Account"]];

export function QuotaCard() {
  const { quota } = useAuth();
  if (!quota) return null;
  const left = quota.free_available ? quota.left : 0;
  return (
    <div className="quota" aria-label="Free runs">
      <div className="row"><span>Free runs today</span><span>{left} of {quota.limit}</span></div>
      <div className="dots">{Array.from({ length: quota.limit }, (_, i) => <i key={i} className={i < left ? "on" : ""} />)}</div>
      {left === 0 && <p className="hint" style={{ marginTop: 8 }}>{quota.capacity_left === 0 ? "Today's free capacity is used up." : "Used up."} Add your own free Gemini key to keep going.</p>}
    </div>
  );
}

function UserBlock() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const name = user.name || user.email.split("@")[0];
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!e.target.closest?.('.rel')) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  return (
    <div className="rel" style={{ display: "block" }}>
      <button className="user btn-ghost btn" style={{ width: "100%", justifyContent: "flex-start", padding: 8 }} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="avatar">{name[0].toUpperCase()}</span>
        <span className="who" style={{ textAlign: "left" }} title={`${name} (${user.email})`}><b>{name}</b><span>{user.email}</span></span>
        <ChevronDown size={16} style={{ marginLeft: "auto" }} />
      </button>
      {open && (
        <div className="menu" style={{ bottom: "calc(100% + 6px)", top: "auto", left: 0, right: "auto" }} onMouseLeave={() => setOpen(false)}>
          <button onClick={() => { setOpen(false); nav("/app/account"); }}><Settings size={16} /> Account</button>
          <button onClick={async () => { await logout(); nav("/"); }}><LogOut size={16} /> Sign out</button>
        </div>
      )}
    </div>
  );
}

export default function Shell() {
  const { user } = useAuth();
  const loc = useLocation();
  if (user === undefined) return <div className="wake"><span className="spinner" style={{ width: 28, height: 28 }} /></div>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return (
    <div className="shell">
      <aside className="side">
        <Logo to="/app/new" />
        <nav aria-label="App">{LINKS.map(([to, Icon, label]) => <NavLink key={to} to={to} className={({ isActive }) => `nav-item ${isActive || (to === "/app/history" && loc.pathname.startsWith("/app/pages")) ? "active" : ""}`}><Icon size={18} /> {label}</NavLink>)}</nav>
        <div className="side-foot"><QuotaCard /><ThemeToggle /><UserBlock /></div>
      </aside>
      <div style={{ minWidth: 0 }}>
        <div className="topbar"><Logo to="/app/new" size={26} /><ThemeToggle /></div>
        <main className="main"><Outlet /></main>
      </div>
      <nav className="tabbar" aria-label="App">{LINKS.map(([to, Icon, label]) => <NavLink key={to} to={to} className={({ isActive }) => (isActive || (to === "/app/history" && loc.pathname.startsWith("/app/pages")) ? "active" : "")}><Icon size={20} />{label}</NavLink>)}</nav>
    </div>
  );
}

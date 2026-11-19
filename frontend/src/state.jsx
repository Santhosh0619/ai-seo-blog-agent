import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";

const safe = (fn, d) => { try { return fn(); } catch { return d; } };

/* ---------- theme: follows the system until the visitor picks one ---------- */
const ThemeCtx = createContext(null);
export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => safe(() => localStorage.getItem("rw_theme"), null) || "system");
  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", mode);
    safe(() => localStorage.setItem("rw_theme", mode));
  }, [mode]);
  return <ThemeCtx.Provider value={{ mode, setMode }}>{children}</ThemeCtx.Provider>;
}
export const useTheme = () => useContext(ThemeCtx);

/* ---------- server info (product name, whether Google sign-in is on) ---------- */
export const MetaCtx = createContext({ google: false });
export const useMeta = () => useContext(MetaCtx);

/* ---------- toasts ---------- */
const ToastCtx = createContext(() => {});
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const toast = useCallback((text) => {
    const id = Math.random();
    setItems((p) => [...p, { id, text }]);
    setTimeout(() => setItems((p) => p.filter((t) => t.id !== id)), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="toasts" role="status" aria-live="polite">{items.map((t) => <div className="toast" key={t.id}>{t.text}</div>)}</div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/* ---------- signed-in user + free-run quota ---------- */
const AuthCtx = createContext(null);
export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = still loading, null = signed out
  const [quota, setQuota] = useState(null);
  const refreshQuota = useCallback(() => api("/api/quota").then(setQuota).catch(() => {}), []);
  const refresh = useCallback(async () => {
    try { setUser((await api("/api/auth/me")).user); } catch { setUser(null); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { if (user) refreshQuota(); else setQuota(null); }, [user, refreshQuota]);
  const logout = useCallback(async () => { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); setUser(null); }, []);
  const value = useMemo(() => ({ user, setUser, quota, refreshQuota, logout, refresh }), [user, quota, refreshQuota, logout, refresh]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}
export const useAuth = () => useContext(AuthCtx);

/* ---------- the user's own Gemini key: this tab only, unless they tick "remember on this device" ---------- */
export function useOwnKey() {
  const [key, setKeyState] = useState(() => safe(() => sessionStorage.getItem("rw_key") || localStorage.getItem("rw_key") || "", ""));
  const [remember, setRemember] = useState(() => safe(() => !!localStorage.getItem("rw_key"), false));
  const store = (k, r) => safe(() => {
    sessionStorage.removeItem("rw_key"); localStorage.removeItem("rw_key");
    if (k) (r ? localStorage : sessionStorage).setItem("rw_key", k);
  });
  const setKey = (k) => { setKeyState(k); store(k, remember); };
  const toggleRemember = (r) => { setRemember(r); store(key, r); };
  return { key, setKey, remember, toggleRemember };
}

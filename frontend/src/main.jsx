import "@fontsource-variable/inter";
import "@fontsource-variable/fraunces";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { PRODUCT } from "./brand";
import { AuthProvider, MetaCtx, ThemeProvider, ToastProvider } from "./state";
import { Sparkles } from "lucide-react";
import Landing from "./pages/Landing";
import Auth from "./pages/Auth";
import Shell from "./pages/Shell";
import NewBlog from "./pages/NewBlog";
import Result from "./pages/Result";
import History from "./pages/History";
import Account from "./pages/Account";
import NotFound from "./pages/NotFound";
import "./styles.css";

// The free host sleeps when idle: show a friendly screen while it wakes up (about a minute).
function Boot({ children }) {
  const [meta, setMeta] = useState(null);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    document.title = `${PRODUCT}: SEO blog pages for any topic`;
    const t = setTimeout(() => setSlow(true), 1500);
    let stop = false;
    const load = () => api("/api/meta").then((m) => !stop && setMeta(m)).catch(() => !stop && setTimeout(load, 2500));
    load();
    return () => { stop = true; clearTimeout(t); };
  }, []);
  if (!meta) {
    return slow ? (
      <div className="wake"><div className="box fade-up">
        <span className="logo-mark" style={{ width: 52, height: 52, borderRadius: 16, margin: "0 auto 18px" }}><Sparkles size={26} /></span>
        <h2 style={{ marginBottom: 8 }}>Waking up the server</h2>
        <p className="muted" style={{ marginBottom: 18 }}>The free host sleeps when nobody is using it. This takes up to a minute, then it is fast.</p>
        <span className="spinner" />
      </div></div>
    ) : null;
  }
  return <MetaCtx.Provider value={meta}>{children}</MetaCtx.Provider>;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <Boot>
            <AuthProvider>
              <Routes>
                <Route path="/" element={<Landing />} />
                <Route path="/login" element={<Auth mode="login" />} />
                <Route path="/signup" element={<Auth mode="signup" />} />
                <Route path="/app" element={<Shell />}>
                  <Route index element={<Navigate to="new" replace />} />
                  <Route path="new" element={<NewBlog />} />
                  <Route path="history" element={<History />} />
                  <Route path="pages/:id" element={<Result />} />
                  <Route path="account" element={<Account />} />
                </Route>
                <Route path="*" element={<NotFound />} />
              </Routes>
            </AuthProvider>
          </Boot>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);

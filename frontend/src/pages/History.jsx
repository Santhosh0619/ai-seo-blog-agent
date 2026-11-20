import { FilePlus2, Globe, Search, Trash2, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../state";
import { Modal, fmtDate } from "../ui";

const gradientFor = (id) => { const h = (id * 47) % 360; return `linear-gradient(135deg, hsl(${h} 68% 56%), hsl(${(h + 70) % 360} 68% 44%))`; };

export default function History() {
  const toast = useToast();
  const [pages, setPages] = useState(null);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("new");
  const [del, setDel] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/pages").then((r) => setPages(r.pages)).catch((e) => setErr(e.message)); }, []);
  const shown = useMemo(() => {
    const t = (pages || []).filter((p) => (p.title + " " + p.primary_keyword + " " + p.topic).toLowerCase().includes(q.toLowerCase()));
    return sort === "score" ? [...t].sort((a, b) => b.score - a.score) : t;
  }, [pages, q, sort]);
  const remove = async () => {
    try { await api(`/api/pages/${del.id}`, { method: "DELETE" }); setPages(pages.filter((p) => p.id !== del.id)); toast("Page deleted"); } catch (e) { toast(e.message); }
    setDel(null);
  };
  return (
    <div>
      <div className="page-head">
        <div><h1 className="display">My pages</h1><p>Only you can see these. Open one to preview, share or download it.</p></div>
        <Link className="btn btn-primary" to="/app/new"><FilePlus2 size={16} /> New blog</Link>
      </div>
      {err && <div className="alert bad">{err}</div>}
      {pages === null && !err && <div className="hgrid">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 290 }} />)}</div>}
      {pages && pages.length === 0 && (
        <div className="empty fade-up"><div className="ico"><FilePlus2 size={28} /></div><h3>No pages yet</h3><p className="muted" style={{ margin: "8px 0 18px" }}>Your first page is one topic away.</p><Link className="btn btn-primary" to="/app/new">Create your first page</Link></div>
      )}
      {pages && pages.length > 0 && (
        <>
          <div className="toolbar">
            <div className="search"><Search size={16} /><input className="input" placeholder="Search your pages" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search your pages" /></div>
            <div className="seg"><button className={sort === "new" ? "on" : ""} onClick={() => setSort("new")}>Newest</button><button className={sort === "score" ? "on" : ""} onClick={() => setSort("score")}>Best score</button></div>
          </div>
          <div className="hgrid">
            {shown.map((p) => (
              <Link key={p.id} to={`/app/pages/${p.id}`} className="card hcard fade-up">
                <div className="hcover" style={p.cover ? undefined : { background: gradientFor(p.id) }}>{p.cover ? <img src={`/img/${p.cover}`} alt="" loading="lazy" /> : null}<span className="pill">{p.score}</span></div>
                <div className="hbody">
                  <h3>{p.title}</h3>
                  <div className="meta">
                    <span>{p.primary_keyword}</span><span>·</span><span>{fmtDate(p.created_at)}</span>
                    {p.shared && <span className="badge ok"><Globe size={11} /> shared</span>}
                    {p.score_before != null && <span className="badge brand"><Wrench size={11} /> repaired</span>}
                    <button className="icon-btn" style={{ marginLeft: "auto", width: 34, height: 34 }} aria-label={`Delete ${p.title}`} onClick={(e) => { e.preventDefault(); setDel(p); }}><Trash2 size={15} /></button>
                  </div>
                </div>
              </Link>
            ))}
          </div>
          {shown.length === 0 && <p className="muted" style={{ textAlign: "center", padding: 40 }}>No pages match “{q}”.</p>}
        </>
      )}
      {del && <Modal title="Delete this page?" onClose={() => setDel(null)} actions={<><button className="btn" onClick={() => setDel(null)}>Cancel</button><button className="btn btn-danger" onClick={remove}><Trash2 size={15} /> Delete</button></>}>“{del.title}” will be deleted for good, with its images and share link.</Modal>}
    </div>
  );
}

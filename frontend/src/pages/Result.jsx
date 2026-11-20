import { Check, ChevronDown, Copy, Download, Globe, ImageIcon, Link2Off, Monitor, Smartphone, Trash2, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { CheckList, GroupCards, KeywordTable } from "../Checks";
import { useToast } from "../state";
import { Alert, Estimate, Modal, ScoreRing, Verified, fmtDate } from "../ui";

const TABS = [["preview", "Preview"], ["score", "SEO score"], ["research", "Keywords"], ["plan", "Plan"], ["images", "Images"]];

function Plan({ plan }) {
  return (
    <div className="card card-pad">
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><h3>{plan.primary_keyword}</h3><span className="badge brand">main keyword</span></div>
      <p className="muted" style={{ marginTop: 6 }}>{plan.angle}</p>
      <div className="chips" style={{ margin: "14px 0" }}>{plan.secondary_keywords.map((k) => <span className="chip" key={k}>{k}</span>)}</div>
      <div className="grid2" style={{ margin: "0 0 14px", gap: 12 }}><div><div className="label">Audience</div>{plan.audience}</div><div><div className="label">Search intent</div>{plan.search_intent}</div></div>
      <p className="muted" style={{ marginBottom: 16 }}>{plan.reasoning}</p>
      <div className="label" style={{ marginBottom: 6 }}>Keyword estimates <Estimate /></div>
      <div className="scroll-x"><table className="table"><thead><tr><th>Keyword</th><th>Intent</th><th>Relevance</th><th>Competition</th><th>Volume</th></tr></thead>
        <tbody>{plan.insights.map((x) => <tr key={x.keyword}><td>{x.keyword}</td><td>{x.intent}</td><td>{x.relevance}</td><td>{x.competition}</td><td>{x.volume_band}</td></tr>)}</tbody></table></div>
      <div className="outline" style={{ marginTop: 18 }}><div className="label">Outline</div><ol>{plan.outline.map((o) => <li key={o.h2}>{o.h2}{o.h3s.length > 0 && <ul>{o.h3s.map((h) => <li key={h}>{h}</li>)}</ul>}</li>)}</ol></div>
    </div>
  );
}

export default function Result() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [p, setP] = useState(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("preview");
  const [mobile, setMobile] = useState(false);
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [sharing, setSharing] = useState(false);
  useEffect(() => {
    if (!menu) return undefined;
    const close = (e) => { if (!e.target.closest?.('.rel')) setMenu(false); };
    const esc = (e) => e.key === 'Escape' && setMenu(false);
    document.addEventListener('mousedown', close); document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [menu]);
  const load = useCallback(() => api(`/api/pages/${id}`).then(setP).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { setP(null); setErr(""); load(); }, [load]);

  if (err) return <div className="empty"><h3>We could not open that page</h3><p className="muted" style={{ margin: "8px 0 16px" }}>{err}</p><Link className="btn" to="/app/history">Back to my pages</Link></div>;
  if (!p) return <div style={{ display: "grid", gap: 14 }}><div className="skeleton" style={{ height: 90 }} /><div className="skeleton" style={{ height: 520 }} /></div>;

  const toggleShare = async () => {
    setSharing(true);
    try { const r = await api(`/api/pages/${p.id}/share`, { method: "POST", body: { enabled: !p.share_url } }); setP({ ...p, share_url: r.share_url }); toast(r.share_url ? "Share link is on" : "Sharing turned off"); }
    catch (e) { toast(e.message); } finally { setSharing(false); }
  };
  const copy = async () => { try { await navigator.clipboard.writeText(p.share_url); toast("Link copied"); } catch { toast("Copy failed: select the link and copy it"); } };
  const del = async () => { try { await api(`/api/pages/${p.id}`, { method: "DELETE" }); toast("Page deleted"); nav("/app/history"); } catch (e) { toast(e.message); } };
  const dl = (f) => `/api/pages/${p.id}/export?format=${f}`;
  const failed = p.checks.filter((c) => c.applicable && !c.passed).length;

  return (
    <div>
      <div className="res-head">
        <ScoreRing score={p.score} size={78} />
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1>{p.title}</h1>
          <p className="muted" style={{ marginTop: 6 }}>{p.primary_keyword} · {p.words.toLocaleString()} words · {fmtDate(p.created_at)}{p.share_url && <> · <span className="badge ok"><Globe size={11} /> shared</span></>}</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn" onClick={toggleShare} disabled={sharing}>{p.share_url ? <><Link2Off size={16} /> Stop sharing</> : <><Globe size={16} /> Share link</>}</button>
          <div className="rel">
            <button className="btn btn-primary" onClick={() => setMenu(!menu)} aria-expanded={menu}><Download size={16} /> Download <ChevronDown size={15} /></button>
            {menu && <div className="menu" onMouseLeave={() => setMenu(false)}>
              <a href={dl("html")} download>Page as one HTML file</a><a href={dl("zip")} download>Zip with images</a><a href={dl("md")} download>Markdown</a><a href={dl("json")} download>Full data (JSON)</a>
            </div>}
          </div>
          <button className="icon-btn" aria-label="Delete page" title="Delete page" onClick={() => setConfirm(true)}><Trash2 size={18} /></button>
        </div>
      </div>

      {p.share_url && (
        <div className="card card-pad" style={{ marginBottom: 18 }}>
          <div className="label" style={{ marginBottom: 6 }}>Anyone with this link can view the page. It is hidden from search engines. Turn it off any time.</div>
          <div className="share-box"><input className="input" readOnly value={p.share_url} onFocus={(e) => e.target.select()} aria-label="Share link" /><button className="btn" onClick={copy}><Copy size={16} /> Copy</button></div>
        </div>
      )}

      <div className="tabs" role="tablist">
        {TABS.map(([k, n]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{n}{k === "score" && failed > 0 && <span className="badge bad">{failed}</span>}</button>)}
      </div>

      {tab === "preview" && (
        <div className="fade-up">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
            <div className="card serp" style={{ flex: 1, minWidth: 280, boxShadow: "none" }}>
              <div className="faint" style={{ fontSize: 12, marginBottom: 6 }}>Search preview</div>
              <div className="url">yoursite.com › {p.post.slug}</div><div className="t">{p.post.seo_title}</div><div className="d">{p.post.meta_description}</div>
            </div>
            <div className="seg"><button className={!mobile ? "on" : ""} onClick={() => setMobile(false)}><Monitor size={14} style={{ verticalAlign: -2 }} /> Desktop</button><button className={mobile ? "on" : ""} onClick={() => setMobile(true)}><Smartphone size={14} style={{ verticalAlign: -2 }} /> Phone</button></div>
          </div>
          <div className={`preview-wrap ${mobile ? "mobile" : ""}`}><iframe title="Page preview" src={`/api/pages/${p.id}/preview`} /></div>
        </div>
      )}

      {tab === "score" && (
        <div className="fade-up card card-pad">
          <div style={{ display: "flex", gap: 22, alignItems: "center", flexWrap: "wrap" }}>
            <ScoreRing score={p.score} size={110} />
            <div><h3>SEO score {p.score} / 100</h3><p className="muted" style={{ marginTop: 4 }}>{failed === 0 ? "Every applicable check passed." : `${failed} check${failed > 1 ? "s" : ""} to improve. Open a check to see how to fix it.`} Computed by code, not by the AI.</p></div>
          </div>
          {p.score_before != null && <div className="ba" style={{ marginTop: 18 }}><Wrench size={16} /> The agent repaired this page once: score {p.score_before} before, {p.score} after.</div>}
          <GroupCards groups={p.research?.groups} />
          <CheckList checks={p.checks} />
        </div>
      )}

      {tab === "research" && (
        <div className="fade-up card card-pad">
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><h3>Keyword research</h3>{p.research.candidates?.[0]?.verified ? <Verified /> : <Estimate />}</div>
          <p className="muted" style={{ margin: "6px 0 14px" }}>{p.research.keyword_source}. {p.research.site_note}</p>
          <div className="label" style={{ marginBottom: 6 }}>Seed phrases</div>
          <div className="chips" style={{ marginBottom: 16 }}>{p.research.seeds.map((s) => <span className="chip" key={s}>{s}</span>)}</div>
          {p.research.facts?.length > 0 && <p className="muted" style={{ marginBottom: 14 }}>Reference text: {p.research.facts.map((f, i) => <span key={f.url}>{i > 0 && ", "}<a href={f.url} target="_blank" rel="noreferrer">{f.title}</a></span>)}</p>}
          <KeywordTable rows={p.research.candidates} />
        </div>
      )}

      {tab === "plan" && <div className="fade-up"><Plan plan={p.plan} /></div>}

      {tab === "images" && (
        <div className="fade-up card card-pad">
          <h3 style={{ marginBottom: 14 }}><ImageIcon size={18} style={{ verticalAlign: -3 }} /> Images on this page</h3>
          {p.images.length === 0 && <p className="muted">This page has no images. You can add your own when you publish it.</p>}
          <div className="gallery">{p.images.map((im) => <figure key={im.token}><img src={im.url} alt={im.alt} loading="lazy" /><figcaption>{im.alt}{im.credit && <><br />{im.credit}</>}</figcaption></figure>)}</div>
        </div>
      )}

      {confirm && <Modal title="Delete this page?" onClose={() => setConfirm(false)} actions={<><button className="btn" onClick={() => setConfirm(false)}>Cancel</button><button className="btn btn-danger" onClick={del}><Trash2 size={15} /> Delete page</button></>}>
        This permanently deletes “{p.title}”, its images and its share link. This cannot be undone.</Modal>}
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { createBlog, getMeta, getPages } from "./api.js";

const STEPS = [
  { id: "research", title: "Keyword research", hint: "Live Google Autocomplete + the site's existing pages" },
  { id: "dedupe", title: "Duplicate & cannibalisation check", hint: "Compare keywords with existing content" },
  { id: "plan", title: "Select keyword & plan content", hint: "AI picks the cluster, topic, slug and outline" },
  { id: "write", title: "Generate the blog", hint: "Title, meta, content, FAQs, links, images, CTA" },
  { id: "validate", title: "SEO validation", hint: "14 on-page checks" },
  { id: "repair", title: "Auto-fix", hint: "One targeted repair pass", optional: true },
  { id: "save", title: "Create & save the page", hint: "Rendered page stored in the test environment" },
];

const Ic = ({ d, size = 18, ...p }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}><path d={d} /></svg>
);
const SPARK = "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z";
const CHECK = "M20 6 9 17l-5-5";
const X = "M18 6 6 18M6 6l12 12";
const ALERT = "M12 3 2 20h20L12 3zM12 10v4M12 17.5v.01";
const EXT = "M14 3h7v7M10 14 21 3M21 14v7H3V3h7";

const Badge = ({ kind, children }) => <span className={`badge ${kind}`}>{children}</span>;
const Verified = () => <Badge kind="ok">Verified</Badge>;
const Estimate = () => <Badge kind="est">AI estimate</Badge>;

function Research({ d }) {
  const shown = d.candidates.slice(0, 14);
  return (
    <>
      <p className="muted"><b>{d.candidates.length}</b> keyword candidates from <b>{d.keyword_source}</b> · <b>{d.site_pages}</b> existing site pages read from <b>{d.site_source}</b> (read-only)</p>
      <div className="chips">{shown.map((c) => <span key={c.keyword} className="chip">{c.keyword}</span>)}{d.candidates.length > 14 && <span className="chip more">+{d.candidates.length - 14} more</span>}</div>
      <p className="legend"><Verified /> Observed directly, not guessed.</p>
    </>
  );
}

function Dedupe({ d }) {
  return (
    <>
      <p className="muted">Checked against <b>{d.site_pages}</b> existing pages: <Badge kind="ok">{d.counts.gap} gaps</Badge> <Badge kind="warn">{d.counts.partial} partial overlap</Badge> <Badge kind="bad">{d.counts.conflict} would cannibalise</Badge></p>
      <div className="table-wrap"><table><thead><tr><th>Keyword</th><th>Status</th><th>Overlap</th><th>Closest existing page</th></tr></thead><tbody>
        {d.candidates.slice(0, 10).map((c) => (
          <tr key={c.keyword}><td>{c.keyword}</td><td><Badge kind={c.status === "gap" ? "ok" : c.status === "partial" ? "warn" : "bad"}>{c.status}</Badge></td>
            <td>{Math.round(c.overlap * 100)}%{c.conflicts > 0 ? ` · ${c.conflicts} pages` : ""}</td><td className="clip">{c.closest[0]?.title ?? "-"}</td></tr>
        ))}
      </tbody></table></div>
    </>
  );
}

function Plan({ d }) {
  return (
    <>
      <div className="kv"><span>Primary keyword</span><b>{d.primary_keyword}</b> {d.primary_verified ? <Verified /> : <Badge kind="est">AI-suggested</Badge>} <Badge kind={d.primary_status === "gap" ? "ok" : "warn"}>{d.primary_status}</Badge></div>
      <div className="kv"><span>Secondary</span><div className="chips">{d.secondary_keywords.map((k, i) => <span key={k} className="chip">{k} {d.secondary_verified[i] ? <Verified /> : null}</span>)}</div></div>
      <div className="kv"><span>Topic</span><b>{d.topic}</b></div>
      <div className="kv"><span>Slug</span><code>/blog/{d.slug}</code></div>
      <div className="kv"><span>Audience</span>{d.audience}</div>
      <div className="kv"><span>Search intent</span>{d.search_intent}</div>
      <p className="muted"><b>Why:</b> {d.reasoning}</p>
      <h4>Keyword analysis <Estimate /></h4>
      <div className="table-wrap"><table><thead><tr><th>Keyword</th><th>Intent</th><th>Relevance</th><th>Competition</th><th>Volume</th></tr></thead><tbody>
        {d.insights.map((i) => <tr key={i.keyword}><td>{i.keyword}</td><td>{i.intent}</td><td>{i.relevance}</td><td>{i.competition}</td><td>{i.volume_band}</td></tr>)}
      </tbody></table></div>
      <h4>Outline</h4>
      <ul className="outline"><li><b>H1</b> {d.topic}</li>{d.outline.map((o) => <li key={o.h2}><b>H2</b> {o.h2}{o.h3s.length > 0 && <ul>{o.h3s.map((h) => <li key={h}><b>H3</b> {h}</li>)}</ul>}</li>)}</ul>
    </>
  );
}

function Write({ d }) {
  return (<><div className="kv"><span>SEO title</span><b>{d.title}</b></div><div className="kv"><span>Meta description</span>{d.meta}</div>
    <p className="muted">{d.words} words · {d.sections} sections · {d.faqs} FAQs · internal links, image ideas with alt text and CTA included</p></>);
}

function Validate({ d }) {
  return (
    <>
      <div className="score"><div className={`ring ${d.score >= 85 ? "good" : d.score >= 60 ? "mid" : "low"}`}>{d.score}</div><span className="muted">SEO score out of 100</span></div>
      <ul className="checks">{d.checks.map((c) => <li key={c.id} className={c.passed ? "pass" : "fail"}><Ic d={c.passed ? CHECK : X} size={15} /> {c.label}{c.detail && <em> · {c.detail}</em>}</li>)}</ul>
    </>
  );
}

function Save({ d }) {
  return (<><div className="kv"><span>Saved page</span><a href={d.url} target="_blank" rel="noreferrer">{d.url}</a></div><p className="muted">SEO score {d.score}/100 · {d.words} words</p></>);
}

const BODY = { research: Research, dedupe: Dedupe, plan: Plan, write: Write, validate: Validate, save: Save, repair: ({ d }) => <p className="muted">{d.note}</p> };

function Step({ def, st }) {
  const status = st?.status ?? "pending";
  const Body = BODY[def.id];
  return (
    <section className={`step ${status}`}>
      <div className="step-head">
        <div className="dotmark">{status === "done" ? <Ic d={CHECK} size={16} /> : status === "running" ? <span className="spin" /> : null}</div>
        <div><h3>{def.title}</h3><p className="muted">{status === "running" ? "Working…" : def.hint}</p></div>
      </div>
      {status === "done" && st.data && <div className="step-body"><Body d={st.data} /></div>}
    </section>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [steps, setSteps] = useState({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [pages, setPages] = useState([]);
  const lock = useRef(false);

  const refresh = useCallback(() => { getPages().then(setPages).catch(() => {}); }, []);
  useEffect(() => { getMeta().then(setMeta).catch(() => setError({ code: "NETWORK", message: "Can't reach the server. Make sure the backend is running, then try again." })); refresh(); }, [refresh]);

  const start = async () => {
    if (lock.current) return;
    lock.current = true; setRunning(true); setSteps({}); setResult(null); setError(null);
    await createBlog({
      onStep: (s) => setSteps((p) => ({ ...p, [s.id]: { status: s.status, data: s.data ?? p[s.id]?.data } })),
      onDone: (r) => { setResult(r); refresh(); },
      onError: (e) => setError(e),
    });
    lock.current = false; setRunning(false);
  };

  const visible = STEPS.filter((s) => !s.optional || steps[s.id]);
  const started = Object.keys(steps).length > 0 || running;

  return (
    <div className="page">
      <header className="top">
        <div className="brand"><div className="logo"><Ic d={SPARK} size={20} /></div><div><b>AI SEO Blog Agent</b><span>Appin Technology Coimbatore · prototype</span></div></div>
        <div className="top-r">
          <Badge kind="est">Test environment</Badge>
          <a className="link" href="/blog" target="_blank" rel="noreferrer">All pages <Ic d={EXT} size={14} /></a>
        </div>
      </header>

      <main className="wrap">
        <section className="hero">
          <h1>Create a complete SEO blog page in one click</h1>
          <p>The agent researches keyword opportunities, avoids topics the site already covers, plans and writes the article, checks it against on-page SEO rules, then builds and saves the page.</p>
          <button className="cta" onClick={start} disabled={running}>{running ? <><span className="spin light" /> Agent is working…</> : <><Ic d={SPARK} /> Create Blog Page</>}</button>
          <small>Uses about 2-3 AI calls per page. Read-only access to the Appin site; nothing is published there.</small>
        </section>

        {error && (
          <div className={`alert ${error.code === "RATE_LIMITED" || error.code === "RUN_LIMIT" || error.code === "BUSY" ? "warn" : ""}`} role="alert">
            <Ic d={ALERT} /><div><p>{error.message}</p>{!running && <button className="retry" onClick={start}>Try again</button>}</div>
          </div>
        )}

        {result && (
          <section className="success">
            <div><b>Blog page created</b><p className="muted">{result.title} · SEO score {result.score}/100 · {result.words} words</p></div>
            <a className="btn" href={result.url} target="_blank" rel="noreferrer">Open page <Ic d={EXT} size={15} /></a>
          </section>
        )}

        {started && <div className="steps">{visible.map((s) => <Step key={s.id} def={s} st={steps[s.id]} />)}</div>}

        {result && (<section className="preview"><h2>Preview</h2><iframe title="Blog preview" src={result.url} /></section>)}

        {pages.length > 0 && (
          <section className="pages"><h2>Pages created</h2>
            <ul>{pages.slice(0, 8).map((p) => <li key={p.slug}><a href={`/blog/${p.slug}`} target="_blank" rel="noreferrer">{p.title}</a><span className="muted">{p.primary_keyword} · {p.seo_score}/100</span></li>)}</ul>
          </section>
        )}
      </main>
    </div>
  );
}

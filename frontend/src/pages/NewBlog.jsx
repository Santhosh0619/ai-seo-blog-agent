import { ArrowRight, Check, ChevronDown, ExternalLink, Eye, EyeOff, Image as ImageIcon, KeyRound, Lightbulb, Loader2, Lock, PenLine, Radar, RotateCcw, Save, ScanSearch, Search, Sparkles, SlidersHorizontal, Wand2, Wrench, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createBlog } from "../api";
import { KEY_URL } from "../brand";
import { CheckList, GroupCards, KeywordTable } from "../Checks";
import { useAuth, useOwnKey } from "../state";
import { Alert, Badge, Estimate, ScoreRing, Verified } from "../ui";

const COUNTRIES = [["us", "United States"], ["in", "India"], ["gb", "United Kingdom"], ["ca", "Canada"], ["au", "Australia"], ["de", "Germany"], ["fr", "France"], ["es", "Spain"], ["br", "Brazil"], ["id", "Indonesia"], ["ae", "UAE"], ["sg", "Singapore"], ["za", "South Africa"], ["ng", "Nigeria"], ["ph", "Philippines"], ["pk", "Pakistan"], ["bd", "Bangladesh"], ["lk", "Sri Lanka"]];
const LANGS = [["en", "English"], ["hi", "Hindi"], ["ta", "Tamil"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["pt", "Portuguese"], ["id", "Indonesian"], ["ar", "Arabic"], ["it", "Italian"], ["nl", "Dutch"], ["tr", "Turkish"], ["ja", "Japanese"]];
const TONES = [["friendly", "Friendly"], ["professional", "Professional"], ["expert", "Expert"], ["casual", "Casual"]];
const EXAMPLES = ["cricket bat for beginners", "how to learn guitar as an adult", "home workout without equipment", "study tips for exams", "indoor plants for small flats", "how to start a podcast"];

const STEPS = [
  { id: "seeds", title: "Understanding your topic", icon: Lightbulb, doing: (t) => `Turning “${t}” into 8 phrases that real people search…`, sum: (d) => `${d.seeds.length} seed phrases` },
  { id: "research", title: "Searching real keyword data", icon: Radar, doing: () => "Asking Google Autocomplete for each phrase, reading your sitemap and Wikipedia…", sum: (d) => `${d.candidates.length} keywords` },
  { id: "dedupe", title: "Checking for overlap", icon: ScanSearch, doing: () => "Comparing every keyword with existing pages so nothing competes…", sum: (d) => `${d.counts.gap} open topics` },
  { id: "plan", title: "Planning the article", icon: Wand2, doing: () => "Choosing the main keyword, a unique angle and the outline…", sum: (d) => d.primary_keyword },
  { id: "write", title: "Writing the draft", icon: PenLine, doing: () => "Writing an original article, FAQs and image ideas…", sum: (d) => `${d.words.toLocaleString()} words` },
  { id: "images", title: "Finding images", icon: ImageIcon, doing: () => "Looking for openly licensed photos for each section…", sum: (d) => `${d.images.length} images` },
  { id: "validate", title: "Scoring SEO", icon: Search, doing: () => "Running the SEO checks on the whole page…", sum: (d) => `score ${d.score}` },
  { id: "repair", title: "Polishing weak spots", icon: Wrench, optional: true, doing: () => "Fixing only the checks that failed, once…", sum: () => "one pass" },
  { id: "save", title: "Saving your page", icon: Save, doing: () => "Saving the page and its images to your account…", sum: () => "saved" },
];

function defaults() {
  const reg = (navigator.language || "en-US").split("-");
  const lang = LANGS.find(([c]) => c === reg[0])?.[0] || "en";
  const country = COUNTRIES.find(([c]) => c === (reg[1] || "").toLowerCase())?.[0] || "us";
  return { topic: "", site_url: "", country, language: lang, audience: "", tone: "friendly", notes: "", author: "", word_target: 1400 };
}

/* ---------- what each step shows on the live canvas ---------- */
function Thinking({ step, topic }) {
  return (
    <div className="canvas">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}><span className="spinner" /><h3 className="typing">{step.doing(topic)}</h3></div>
      <div style={{ display: "grid", gap: 10 }}>{[92, 78, 85, 60].map((w, i) => <div key={i} className="skeleton" style={{ height: 16, width: `${w}%` }} />)}</div>
    </div>
  );
}

function StepView({ id, d, topic }) {
  if (id === "seeds") return (
    <div className="canvas"><h3>Seed phrases</h3><p className="muted">What a real person might type. Next, Google tells us what people actually search.</p>
      <div className="chips" style={{ marginTop: 16 }}>{d.seeds.map((s, i) => <span key={s} className="chip pop" style={{ animationDelay: `${i * 70}ms` }}><Search size={13} /> {s}</span>)}</div></div>
  );
  if (id === "research") return (
    <div className="canvas">
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><h3>Keywords found</h3>{d.candidates[0]?.verified ? <Verified /> : <Estimate />}</div>
      <p className="muted">{d.keyword_source}. {d.site_note}</p>
      {d.facts.length > 0 && <p className="muted" style={{ marginTop: 6 }}>Reference text: {d.facts.map((f, i) => <span key={f.url}>{i > 0 && ", "}<a href={f.url} target="_blank" rel="noreferrer">{f.title}</a></span>)}</p>}
      <div className="kwlist">{d.candidates.map((c) => <div className="kw" key={c.keyword}><span>{c.keyword}</span>{c.verified ? <Verified /> : <Estimate />}</div>)}</div>
    </div>
  );
  if (id === "dedupe") return (
    <div className="canvas"><h3>Overlap check</h3>
      <p className="muted">{d.pages} existing pages compared ({d.site_pages} from your site, {d.own_pages} of your earlier pages). Green means the topic is open.</p>
      <div className="chips" style={{ margin: "14px 0" }}><span className="status gap">{d.counts.gap} gap</span><span className="status partial">{d.counts.partial} partial</span><span className="status conflict">{d.counts.conflict} conflict</span></div>
      <KeywordTable rows={d.candidates.slice(0, 12).map((c) => ({ ...c, verified: true }))} /></div>
  );
  if (id === "plan") return (
    <div className="canvas">
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><h3>{d.primary_keyword}</h3>{d.primary_verified ? <Verified /> : <Estimate />}<span className={`status ${d.primary_status}`}>{d.primary_status}</span></div>
      <p className="muted" style={{ marginTop: 6 }}>{d.angle}</p>
      <div className="chips" style={{ margin: "14px 0" }}>{d.secondary_keywords.map((k, i) => <span className="chip" key={k}>{k} {d.secondary_verified[i] ? <Check size={12} color="var(--ok)" /> : <Sparkles size={12} color="var(--warn)" />}</span>)}</div>
      <div className="grid2" style={{ margin: "0 0 14px", gap: 12 }}>
        <div><div className="label">Audience</div>{d.audience}</div><div><div className="label">Search intent</div>{d.search_intent}</div>
      </div>
      <p className="muted" style={{ marginBottom: 14 }}>{d.reasoning}</p>
      <div className="label" style={{ marginBottom: 6 }}>Keyword estimates <Estimate /></div>
      <div className="scroll-x"><table className="table"><thead><tr><th>Keyword</th><th>Intent</th><th>Relevance</th><th>Competition</th><th>Volume</th></tr></thead>
        <tbody>{d.insights.map((x) => <tr key={x.keyword}><td>{x.keyword}</td><td>{x.intent}</td><td>{x.relevance}</td><td>{x.competition}</td><td>{x.volume_band}</td></tr>)}</tbody></table></div>
      <div className="outline" style={{ marginTop: 16 }}><div className="label">Outline</div><ol>{d.outline.map((o) => <li key={o.h2}>{o.h2}{o.h3s.length > 0 && <ul>{o.h3s.map((h) => <li key={h}>{h}</li>)}</ul>}</li>)}</ol></div>
    </div>
  );
  if (id === "write") return (
    <div className="canvas"><h3>Draft written</h3><p className="muted">{d.words.toLocaleString()} words, {d.sections} sections, {d.faqs} FAQs.</p>
      <div className="card serp" style={{ marginTop: 16, boxShadow: "none" }}><div className="faint" style={{ fontSize: 12, marginBottom: 6 }}>Search preview</div><div className="t">{d.title}</div><div className="d">{d.meta}</div></div></div>
  );
  if (id === "images") return (
    <div className="canvas"><h3>Images</h3><p className="muted">Each page gets a real image per section, with credit where the licence asks for it.</p>
      <div style={{ display: "grid", gap: 10, marginTop: 14 }}>{d.images.map((im, i) => <div className="kw" key={i}><span><ImageIcon size={14} style={{ verticalAlign: -2 }} /> Image {i + 1}</span><span className="muted" style={{ fontSize: 13 }}>{im.credit || (im.source === "cover" ? "Generated cover" : im.source)}</span></div>)}</div></div>
  );
  if (id === "validate") return (
    <div className="canvas">
      <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}><ScoreRing score={d.score} /><div><h3>SEO score</h3><p className="muted">Computed by code, not by the AI.</p></div></div>
      {d.repaired && d.score_before != null && <div className="ba" style={{ marginTop: 14 }}><Wrench size={16} /> Repaired once: {d.score_before} to {d.score}</div>}
      <GroupCards groups={d.groups} /><CheckList checks={d.checks} />
    </div>
  );
  if (id === "repair") return <div className="canvas"><h3>Polishing</h3><p className="muted">{d.note}</p></div>;
  if (id === "save") return <div className="canvas"><h3>Saved</h3><p className="muted">“{d.title}” is in your account.</p></div>;
  return null;
}

export default function NewBlog() {
  const nav = useNavigate();
  const [q] = useSearchParams();
  const { quota, refreshQuota } = useAuth();
  const own = useOwnKey();
  const [form, setForm] = useState(() => ({ ...defaults(), topic: q.get("topic") || "" }));
  const [custom, setCustom] = useState(false);
  const [adv, setAdv] = useState(false);
  const [pulse, setPulse] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState({});
  const [sel, setSel] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [notice, setNotice] = useState("");
  const keyRef = useRef(null);
  const abort = useRef(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  useEffect(() => () => abort.current?.abort(), []);

  const freeLeft = quota ? (quota.free_available ? quota.left : 0) : null;
  const order = useMemo(() => STEPS.filter((s) => !s.optional || steps[s.id]), [steps]);
  const doneCount = order.filter((s) => steps[s.id]?.status === "done").length;
  const running_id = order.find((s) => steps[s.id]?.status === "running")?.id;
  const current = sel || running_id || [...order].reverse().find((s) => steps[s.id]?.status === "done")?.id;

  const needKey = (msg) => { setAdv(true); setPulse(true); setNotice(msg); setTimeout(() => keyRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 80); };

  const start = async (e) => {
    e?.preventDefault();
    if (form.topic.trim().length < 3) return setErr({ message: "Please type your topic first (at least 3 characters)." });
    setErr(null); setNotice("");
    if (!own.key && quota && !quota.free_available) {
      return needKey(quota.capacity_left === 0 ? "Today's free capacity is used up. Paste your own free Gemini key below to continue." : `You used your ${quota.limit} free runs for today. Paste your own free Gemini key below to keep creating pages.`);
    }
    abort.current = new AbortController();
    setRunning(true); setSteps({}); setSel(null); setResult(null);
    await createBlog({ ...form, topic: form.topic.trim() }, {
      key: own.key.trim(), signal: abort.current.signal,
      onStep: (s) => setSteps((p) => ({ ...p, [s.id]: { status: s.status, data: s.data ?? p[s.id]?.data } })),
      onDone: (r) => { setResult(r); setRunning(false); refreshQuota(); },
      onError: (er, step) => {
        setRunning(false); setErr(er); refreshQuota();
        if (step) setSteps((p) => ({ ...p, [step]: { ...p[step], status: "failed" } }));
        if (er.needsKey) needKey(er.message);
      },
    });
    setRunning(false);
  };
  const reset = () => { abort.current?.abort(); setSteps({}); setResult(null); setErr(null); setRunning(false); setSel(null); };
  const started = Object.keys(steps).length > 0;

  return (
    <div>
      <div className="page-head">
        <div><h1 className="display">{started ? "Your agent is on it" : "Create a blog page"}</h1><p>{started ? <>Topic: <b>{form.topic}</b></> : "Type a topic. The agent researches, plans, writes, checks and saves a page for you."}</p></div>
        {freeLeft !== null && !own.key && <Badge kind={freeLeft > 0 ? "brand" : "est"} icon={Sparkles}>{freeLeft} of {quota.limit} free runs left today</Badge>}
        {own.key && <Badge kind="ok" icon={KeyRound}>Using your own Gemini key</Badge>}
      </div>

      {!started && (
        <form className="card composer fade-up" onSubmit={start}>
          <label className="sr" htmlFor="topic">Topic</label>
          <div className="topic">
            <Wand2 size={22} />
            <input id="topic" value={form.topic} onChange={set("topic")} placeholder="What should the page be about?" maxLength={120} autoFocus />
            <button className="btn btn-primary btn-lg" type="submit" disabled={running}>{running ? <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} /> : <Sparkles size={18} />} Create blog page</button>
          </div>
          <div className="chips" style={{ marginTop: 14 }}>
            <span className="hint" style={{ alignSelf: "center" }}>Try:</span>
            {EXAMPLES.map((x) => <button type="button" className="chip" key={x} onClick={() => setForm({ ...form, topic: x })}>{x}</button>)}
          </div>
          {err && <div style={{ marginTop: 16 }}><Alert kind="bad" onClose={() => setErr(null)}>{err.message}</Alert></div>}
          {notice && <div style={{ marginTop: 16 }}><Alert kind="warn">{notice}</Alert></div>}

          <button type="button" className={`expander ${custom ? "open" : ""}`} onClick={() => setCustom(!custom)} aria-expanded={custom}><SlidersHorizontal size={17} /> Customize <span className="hint">website, country, language, tone, notes</span><ChevronDown className="chev" size={18} /></button>
          {custom && (
            <div className="formgrid fade-up">
              <div className="field span2"><label htmlFor="site">Your website (optional)</label><input id="site" className="input" value={form.site_url} onChange={set("site_url")} placeholder="https://example.com" inputMode="url" /><span className="hint">We only read your public sitemap, to avoid topics you already cover and to link to your pages. We never change your site.</span></div>
              <div className="field"><label htmlFor="country">Country</label><select id="country" className="select" value={form.country} onChange={set("country")}>{COUNTRIES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></div>
              <div className="field"><label htmlFor="lang">Language</label><select id="lang" className="select" value={form.language} onChange={set("language")}>{LANGS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></div>
              <div className="field"><label htmlFor="aud">Audience (optional)</label><input id="aud" className="input" value={form.audience} onChange={set("audience")} placeholder="e.g. parents of young players" maxLength={120} /></div>
              <div className="field"><label htmlFor="author">Author name (optional)</label><input id="author" className="input" value={form.author} onChange={set("author")} placeholder="Shown on the page" maxLength={60} /></div>
              <div className="field span2"><span className="label">Tone</span><div className="seg" role="group" aria-label="Tone" style={{ flexWrap: "wrap" }}>{TONES.map(([v, n]) => <button type="button" key={v} className={form.tone === v ? "on" : ""} onClick={() => setForm({ ...form, tone: v })}>{n}</button>)}</div></div>
              <div className="field span2"><label htmlFor="len">Length: about {form.word_target.toLocaleString()} words</label><input id="len" className="range" type="range" min={800} max={2200} step={100} value={form.word_target} onChange={(e) => setForm({ ...form, word_target: +e.target.value })} /></div>
              <div className="field span2"><label htmlFor="notes">Facts the writer may use (optional)</label><textarea id="notes" className="textarea" value={form.notes} onChange={set("notes")} maxLength={1500} placeholder="Prices, features, your own experience, anything true. The writer may only use numbers that appear here or in the reference text." /></div>
            </div>
          )}

          <button type="button" className={`expander ${adv ? "open" : ""}`} onClick={() => setAdv(!adv)} aria-expanded={adv} style={{ marginTop: custom ? 4 : 0, borderTop: custom ? "1px solid var(--line)" : undefined }}><KeyRound size={17} /> Use your own Gemini key <span className="hint">no daily limit</span><ChevronDown className="chev" size={18} /></button>
          {adv && (
            <div className={`keybox fade-up ${pulse ? "pulse" : ""}`} ref={keyRef}>
              <div className="keyrow">
                <input className="input" type={showKey ? "text" : "password"} value={own.key} autoComplete="off" spellCheck={false} placeholder="Paste your Gemini API key" aria-label="Your Gemini API key"
                  onFocus={() => setPulse(false)} onClick={() => setPulse(false)} onChange={(e) => own.setKey(e.target.value.trim())} />
                <button type="button" className="btn" onClick={() => setShowKey(!showKey)} aria-label={showKey ? "Hide key" : "Show key"}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                {own.key && <button type="button" className="btn" onClick={() => { own.setKey(""); }}><X size={16} /> Clear</button>}
              </div>
              <p className="privacy"><Lock size={15} /> <span>Your key is sent securely to our server only to run your blog. It is never saved or logged. It stays in this browser tab and is forgotten when you close it.</span></p>
              <label className="check" style={{ marginTop: 10 }}><input type="checkbox" checked={own.remember} onChange={(e) => own.toggleRemember(e.target.checked)} /> Remember it on this device (off by default)</label>
              <p className="hint" style={{ marginTop: 10 }}>Free keys are made in Google AI Studio. <a href={KEY_URL} target="_blank" rel="noreferrer">Get a free key <ExternalLink size={12} style={{ verticalAlign: -1 }} /></a>. You can delete the key there at any time.</p>
            </div>
          )}
        </form>
      )}

      {started && (
        <>
          {result && (
            <div className="success">
              <span className="big"><Check size={26} strokeWidth={3} /></span>
              <div style={{ flex: 1 }}><h3>Your page is ready</h3><p className="muted">{result.title} · score {result.score}/100 · {result.words.toLocaleString()} words{result.repaired && result.score_before != null ? ` · repaired once (${result.score_before} to ${result.score})` : ""}</p></div>
              <button className="btn btn-primary" onClick={() => nav(`/app/pages/${result.id}`)}>Open page <ArrowRight size={16} /></button>
            </div>
          )}
          {err && !running && (
            <div style={{ marginBottom: 18 }}><Alert kind="bad">{err.message}{err.needsKey && <> <button className="btn btn-sm" style={{ marginLeft: 8 }} onClick={() => { reset(); setAdv(true); setPulse(true); }}>Add my key</button></>}</Alert></div>
          )}
          <div className="run">
            <aside className="card timeline">
              <div className="tl-head"><b>{result ? "Finished" : err ? "Stopped" : "Working…"}</b><span className="hint">{doneCount} of {Math.max(order.length, 8)} steps</span></div>
              <div className="progress"><i style={{ width: `${Math.round((doneCount / Math.max(order.length, 8)) * 100)}%` }} /></div>
              <div className="tl">
                {STEPS.filter((s) => !s.optional || steps[s.id]).map((s) => {
                  const st = steps[s.id];
                  const status = st?.status || "pending";
                  const Icon = s.icon;
                  return (
                    <button key={s.id} className={`tl-item ${status} ${current === s.id ? "sel" : ""}`} disabled={!st?.data && status !== "running"} onClick={() => setSel(s.id)}>
                      <span className="tl-dot">{status === "done" ? <Check size={14} strokeWidth={3} /> : status === "failed" ? <X size={14} strokeWidth={3} /> : <Icon size={14} />}</span>
                      <span><b>{s.title}</b><span>{status === "done" && st.data ? s.sum(st.data) : status === "running" ? "in progress" : status === "failed" ? "failed" : "waiting"}</span></span>
                    </button>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                {running && <button className="btn btn-sm" onClick={reset}><X size={14} /> Cancel</button>}
                {!running && <button className="btn btn-sm" onClick={reset}><RotateCcw size={14} /> New topic</button>}
              </div>
            </aside>
            <section style={{ minWidth: 0 }}>
              {current && steps[current]?.data ? <StepView key={current} id={current} d={steps[current].data} topic={form.topic} /> : current ? <Thinking step={STEPS.find((s) => s.id === current)} topic={form.topic} /> : null}
            </section>
          </div>
        </>
      )}
      {!started && <p className="hint" style={{ marginTop: 18, textAlign: "center" }}>Each page takes about a minute. Review it before you publish, and never publish text you have not read.</p>}
    </div>
  );
}

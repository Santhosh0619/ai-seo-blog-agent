import { ArrowRight, BadgeCheck, Check, FileDown, Gauge, Image as ImageIcon, KeyRound, Layers, Lock, PenLine, Radar, Search, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PRODUCT } from "../brand";
import { useAuth } from "../state";
import { Logo, ScoreRing, ThemeToggle } from "../ui";

export const DEMO_STEPS = [
  ["Understanding your topic", "8 seed phrases"], ["Searching real keyword data", "38 keywords"], ["Checking for overlap", "12 gaps"],
  ["Planning the article", "1 main + 5 side"], ["Writing the draft", "1,420 words"], ["Finding images", "3 images"], ["Scoring 22 SEO checks", "score 94"], ["Saving your page", "done"],
];

export function DemoSteps({ speed = 1300 }) {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => (x + 1) % (DEMO_STEPS.length + 2)), speed); return () => clearInterval(t); }, [speed]);
  return (
    <div className="demo-steps">
      {DEMO_STEPS.map(([label, out], k) => (
        <div key={label} className={`dstep ${k < i ? "done" : ""} ${k === i ? "on" : ""}`}>
          <span className="dot">{k < i ? <Check size={13} strokeWidth={3} /> : k === i ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2, borderColor: "rgba(255,255,255,.4)", borderTopColor: "#fff" }} /> : k + 1}</span>
          {label}<small>{k < i ? out : ""}</small>
        </div>
      ))}
    </div>
  );
}

const FEATURES = [
  [Radar, "Real keyword research", "Keywords come from live Google Autocomplete for your topic and country. Every one is labelled Verified, and the AI's guesses are labelled as guesses."],
  [Layers, "No competing pages", "Reads your sitemap (optional) and your earlier pages, then picks a topic you do not already cover, so your own pages never fight each other."],
  [Gauge, "22 transparent SEO checks", "Titles, keyword placement, structure, readability, FAQs, schema and trust signals. Each check says why it matters and how to fix it."],
  [PenLine, "Original, not generic", "A unique angle every time, a banned list of stock AI phrases, and a rule against invented statistics or prices."],
  [ImageIcon, "Real images with credit", "Openly licensed photos with the photographer's credit, or a clean generated cover. Never a broken image."],
  [Lock, "Private by default", "You only ever see your own pages. Share a page with a link when you choose, or download it as HTML and host it yourself."],
];

const FAQ = [
  ["Is it really free?", "Yes. Everyone gets 2 free blog pages a day on our shared Gemini key. You can add your own free Gemini key for unlimited runs. There is no card and no trial."],
  ["Where does the keyword data come from?", "Google Autocomplete suggestions for your topic, the sitemap of your own site (if you add it) and Wikipedia for reference text. Search volume and competition are not available for free, so those are labelled AI estimates (low, medium, high)."],
  ["Is my Gemini key safe?", "Your key is sent securely to our server only to run your blog. It is never saved or logged. By default it stays in this browser tab only."],
  ["Will Google accept AI-written pages?", "Google rewards helpful, original content however it is written. No tool can promise rankings. Review and edit every page before you publish it."],
  ["Can I publish the pages?", "Yes. Download a self-contained HTML file or a zip with images, or copy the Markdown, and publish it on your own site."],
  ["Does it touch my website?", "Only to read your public sitemap (if you give one). It never logs in, never writes and never publishes anything to your site."],
];

export default function Landing() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [topic, setTopic] = useState("");
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => { const f = () => setScrolled(window.scrollY > 8); f(); window.addEventListener("scroll", f); return () => window.removeEventListener("scroll", f); }, []);
  const go = (e) => {
    e.preventDefault();
    const q = topic.trim() ? `?topic=${encodeURIComponent(topic.trim())}` : "";
    nav(user ? `/app/new${q}` : `/signup${q}`);
  };
  return (
    <>
      <header className={`nav ${scrolled ? "scrolled" : ""}`}>
        <div className="container nav-in">
          <Logo />
          <nav className="nav-links" aria-label="Main">
            <a className="link" href="#how">How it works</a><a className="link" href="#data">Honest data</a><a className="link" href="#faq">FAQ</a>
            <ThemeToggle />
            {user ? <Link className="btn btn-primary btn-sm" to="/app/new">Open app</Link> : <>
              <Link className="link" to="/login">Sign in</Link><Link className="btn btn-primary btn-sm" to="/signup">Get started</Link></>}
          </nav>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="mesh" />
          <div className="container">
            <div className="hero-grid">
              <div>
                <span className="eyebrow fade-up"><i>New</i> An AI agent that researches, writes and scores SEO pages</span>
                <h1 className="display fade-up">Turn any topic into a page <span className="grad-text">Google wants to read.</span></h1>
                <p className="lead fade-up">Type a topic. The agent finds real keywords, avoids pages you already have, writes an original article with real images, and checks it against 22 SEO rules. Free to try.</p>
                <form className="cmd fade-up" onSubmit={go}>
                  <Search className="lead-icon" size={20} />
                  <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Try: cricket bat for beginners" aria-label="Your topic" maxLength={120} />
                  <button className="btn btn-primary btn-lg" type="submit">Create blog page <ArrowRight size={18} /></button>
                </form>
                <div className="hero-note">
                  <span><BadgeCheck size={15} /> 2 free pages a day</span><span><ShieldCheck size={15} /> Your data stays private</span><span><KeyRound size={15} /> Or bring your own Gemini key</span>
                </div>
              </div>
              <div className="card demo-card fade-up">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>Agent at work</b><span className="badge brand"><Sparkles size={12} /> live</span>
                </div>
                <DemoSteps />
              </div>
            </div>

            <div className="demo">
              <div className="card serp">
                <div className="faint" style={{ fontSize: 12, marginBottom: 8 }}>What searchers see</div>
                <div className="url">yoursite.com › cricket-bat-for-beginners</div>
                <div className="t">Cricket Bat for Beginners: A Practical Guide</div>
                <div className="d">Learn how to choose, size and care for your first bat. Clear advice, common mistakes and simple routines that help you start with confidence.</div>
              </div>
              <div className="card card-pad" style={{ display: "flex", gap: 20, alignItems: "center" }}>
                <ScoreRing score={94} size={92} />
                <div style={{ flex: 1 }}>
                  <b>SEO score, with the reasons</b>
                  <div className="muted" style={{ fontSize: 14, margin: "4px 0 10px" }}>Every failed check tells you why it matters and how to fix it.</div>
                  <div className="chips"><span className="badge ok"><Check size={12} /> Title and meta</span><span className="badge ok"><Check size={12} /> FAQ schema</span><span className="badge est">Readability</span></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section alt" id="features">
          <div className="container">
            <h2 className="display">Everything a real SEO page needs, <span className="grad-text">checked, not guessed.</span></h2>
            <p className="sub">Built for people who publish: bloggers, shop owners, teachers, clubs and small teams. No SEO degree needed.</p>
            <div className="grid3">
              {FEATURES.map(([Icon, t, d]) => (
                <div className="card feat" key={t}><div className="ico"><Icon size={21} /></div><h3>{t}</h3><p>{d}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section className="section" id="how">
          <div className="container">
            <h2 className="display">From topic to finished page in about a minute.</h2>
            <div className="steps5">
              {[["Tell it your topic", "Add your website, country and language if you like."], ["It researches", "Real suggestions, your sitemap, reference text."], ["It plans", "One main keyword, a unique angle, a clear outline."], ["It writes and checks", "Original text, images, then 22 checks and one repair pass."], ["You review and publish", "Preview, share a link or download the page."]].map(([t, d]) => (
                <div className="st" key={t}><h3>{t}</h3><p>{d}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section className="section alt" id="data">
          <div className="container">
            <h2 className="display">Honest about what is real.</h2>
            <p className="sub">Most SEO tools hide where their numbers come from. We label every data point.</p>
            <div className="honest">
              <div className="card">
                <span className="badge ok"><Check size={12} /> Verified</span>
                <h3 style={{ margin: "12px 0 8px" }}>Observed directly</h3>
                <ul className="muted" style={{ paddingLeft: 18, margin: 0, display: "grid", gap: 6 }}>
                  <li>Keyword suggestions from live Google Autocomplete</li>
                  <li>Pages from your own sitemap</li>
                  <li>Reference text and sources from Wikipedia</li>
                  <li>The 22 SEO checks, computed by code</li>
                </ul>
              </div>
              <div className="card">
                <span className="badge est"><Sparkles size={12} /> AI estimate</span>
                <h3 style={{ margin: "12px 0 8px" }}>Judged by the AI, shown as a range</h3>
                <ul className="muted" style={{ paddingLeft: 18, margin: 0, display: "grid", gap: 6 }}>
                  <li>Search volume: low, medium or high</li>
                  <li>Competition: low, medium or high</li>
                  <li>Search intent and relevance</li>
                  <li>We never invent exact numbers</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="faq">
          <div className="container" style={{ maxWidth: 820 }}>
            <h2 className="display">Questions, answered.</h2>
            <div className="faq" style={{ marginTop: 28 }}>
              {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}
            </div>
            <div className="cta-band">
              <h2 className="display">Your next page is one topic away.</h2>
              <p>Start free. No card, no setup. Bring your own Gemini key whenever you want unlimited runs.</p>
              <Link className="btn btn-lg" to={user ? "/app/new" : "/signup"}><Wand2 size={18} /> Create your first page</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="site"><div className="container row"><span>{PRODUCT}: an AI SEO blog agent. Built with FastAPI, LangGraph and Gemini.</span><span><FileDown size={14} style={{ verticalAlign: -2 }} /> Your pages are yours to download.</span></div></footer>
    </>
  );
}

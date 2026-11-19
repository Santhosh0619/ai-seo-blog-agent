import { Link } from "react-router-dom";
import { PRODUCT } from "../brand";
import { Logo, ThemeToggle } from "../ui";

export default function Privacy() {
  return (
    <>
      <header className="nav scrolled"><div className="container nav-in"><Logo /><div className="nav-links"><ThemeToggle /><Link className="btn btn-primary btn-sm" to="/signup">Get started</Link></div></div></header>
      <main className="container" style={{ maxWidth: 760, padding: "40px 24px 80px" }}>
        <h1 className="display" style={{ fontSize: "clamp(2rem,5vw,3rem)", marginBottom: 8 }}>Privacy</h1>
        <p className="muted">How {PRODUCT} handles your data, in plain words.</p>
        <div className="faq" style={{ marginTop: 28 }}>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>What we store</h2>
          <p className="muted">Your email address (and your name if you give one), a password hash if you sign up with a password, the pages you create (text, images and the research behind them), and a short history of your runs so we can apply the free daily limit.</p>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>What we never store</h2>
          <p className="muted">Your own Gemini API key. It is sent securely to our server only to run your blog, and it is never saved or logged. By default it stays in your browser tab and is forgotten when you close it.</p>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>Who can see your pages</h2>
          <p className="muted">Only you. A page becomes viewable by others only if you turn on its share link, and you can turn it off at any time. Shared pages are hidden from search engines.</p>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>Google sign-in</h2>
          <p className="muted">If you continue with Google, we receive your name and verified email address from Google, and nothing else. We do not access your Google files, contacts or calendar.</p>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>AI providers</h2>
          <p className="muted">Your topic and notes are sent to Google Gemini to write your page. Free Gemini keys may let Google use prompts to improve its products, so please do not put private information in your topic or notes. Keyword suggestions come from Google Autocomplete and reference text from Wikipedia.</p>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>Your controls</h2>
          <p className="muted">From the Account page you can download all your data or delete your account. Deleting removes your account, pages, images and share links permanently.</p>
          <h2 style={{ fontSize: 20, margin: "28px 0 8px" }}>Questions</h2>
          <p className="muted">Open an issue at <a href="https://github.com/Santhosh0619/ai-seo-blog-agent/issues" target="_blank" rel="noreferrer">github.com/Santhosh0619/ai-seo-blog-agent</a>.</p>
        </div>
      </main>
    </>
  );
}

import { Check, Minus, X } from "lucide-react";
import { Estimate, Verified } from "./ui";

export const GROUP_ORDER = ["onpage", "content", "trust", "tech"];

export function GroupCards({ groups }) {
  return (
    <div className="groups">
      {GROUP_ORDER.filter((g) => groups?.[g]).map((g) => {
        const x = groups[g];
        return (
          <div className="group" key={g}>
            <b>{x.name}</b><div className="n">{x.score}<span className="faint" style={{ fontSize: 14, fontWeight: 600 }}> / 100</span></div>
            <div className="gbar"><i style={{ width: `${x.score}%` }} /></div>
            <div className="hint" style={{ marginTop: 6 }}>{x.passed} of {x.total} checks passed</div>
          </div>
        );
      })}
    </div>
  );
}

export function CheckList({ checks, defaultOpenFailed = true }) {
  const rank = (c) => (!c.applicable ? 2 : c.passed ? 1 : 0);
  const sorted = [...checks].sort((a, b) => rank(a) - rank(b));
  return (
    <ul className="checks">
      {sorted.map((c) => {
        const cls = !c.applicable ? "na" : c.passed ? "pass" : "fail";
        const Icon = !c.applicable ? Minus : c.passed ? Check : X;
        return (
          <li key={c.id}>
            <details className={`chk ${cls}`} open={defaultOpenFailed && cls === "fail"}>
              <summary><span className="ic"><Icon size={13} strokeWidth={3} /></span><span>{c.label}</span><span className="det">{c.applicable ? c.detail : "not applicable"}</span></summary>
              <div className="body">
                <div><b>Why it matters:</b> {c.why}</div>
                {cls === "fail" && <div><b>How to fix:</b> {c.fix}</div>}
                {!c.applicable && <div>This check is skipped for this page, so it does not affect the score.</div>}
              </div>
            </details>
          </li>
        );
      })}
    </ul>
  );
}

export function KeywordTable({ rows }) {
  return (
    <div className="scroll-x">
      <table className="table">
        <thead><tr><th>Keyword</th><th>Data</th><th>Overlap</th><th>Closest existing page</th></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.keyword}>
              <td><b>{c.keyword}</b></td>
              <td>{c.verified ? <Verified /> : <Estimate />}</td>
              <td><span className={`status ${c.status}`}>{c.status} · {Math.round(c.overlap * 100)}%</span></td>
              <td className="muted">{c.closest?.[0]?.title || "none"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

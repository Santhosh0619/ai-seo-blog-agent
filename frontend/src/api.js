const NETWORK = { code: "NETWORK", message: "Can't reach the server. Make sure the backend is running, then try again." };

async function readError(res) {
  try { const b = await res.json(); if (b?.error) return b.error; } catch { /* not JSON */ }
  return { code: "UPSTREAM_ERROR", message: "Something went wrong on our side. Please try again in a moment." };
}

export async function getMeta() {
  const r = await fetch("/api/meta");
  if (!r.ok) throw new Error("meta");
  return r.json();
}

export async function getPages() {
  const r = await fetch("/api/pages");
  if (!r.ok) throw new Error("pages");
  return (await r.json()).pages;
}

/** Start the agent and stream its progress. Callbacks: onStep(step), onDone(result), onError(err). */
export async function createBlog({ signal, onStep, onDone, onError }) {
  let res;
  try {
    res = await fetch("/api/blog/create", { method: "POST", signal });
  } catch (e) {
    if (e.name !== "AbortError") onError(NETWORK);
    return;
  }
  if (!res.ok) return onError(await readError(res));

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", finished = false;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) !== -1) {
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        const name = /^event: (.+)$/m.exec(block)?.[1];
        const raw = /^data: (.+)$/m.exec(block)?.[1];
        if (!name || !raw) continue;
        const data = JSON.parse(raw);
        if (name === "step") onStep(data);
        else if (name === "done") { finished = true; onDone(data); }
        else if (name === "error") { finished = true; onError(data); }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") onError(NETWORK);
    return;
  }
  if (!finished) onError(NETWORK);
}

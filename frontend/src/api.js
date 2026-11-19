// Small fetch helpers. Cookies (the login session) are sent automatically because the API is same-origin.
export class ApiError extends Error {
  constructor(code, message, status, needsKey = false) {
    super(message);
    this.code = code; this.status = status; this.needsKey = needsKey;
  }
}

async function toError(res) {
  let body = null;
  try { body = await res.json(); } catch { /* not json */ }
  const e = body?.error;
  if (e) return new ApiError(e.code, e.message, res.status, !!e.needs_key);
  if (res.status === 422) return new ApiError("BAD_INPUT", "Please check the form and try again.", 422);
  return new ApiError("NETWORK", "Something went wrong. Please try again.", res.status);
}

export async function api(path, { method = "GET", body, headers } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method, credentials: "same-origin",
      headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("NETWORK", "Cannot reach the server. Check your connection and try again.", 0);
  }
  if (!res.ok) throw await toError(res);
  return res.status === 204 ? null : res.json();
}

// Creating a blog streams Server-Sent Events over a POST (EventSource cannot POST), so we read the stream by hand.
// The user's own Gemini key (if any) goes in a header, never in the URL or the body.
export async function createBlog(form, { key, onStep, onDone, onError, signal }) {
  let res;
  try {
    res = await fetch("/api/blog/create", {
      method: "POST", credentials: "same-origin", signal,
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...(key ? { "X-Gemini-Key": key } : {}) },
      body: JSON.stringify(form),
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    return onError(new ApiError("NETWORK", "Cannot reach the server. Check your connection and try again.", 0));
  }
  if (!res.ok) return onError(await toError(res));
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let finished = false;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const name = /^event: (.*)$/m.exec(block)?.[1];
        const data = /^data: (.*)$/m.exec(block)?.[1];
        if (!name || !data) continue;
        const d = JSON.parse(data);
        if (name === "step") onStep(d);
        else if (name === "done") { finished = true; onDone(d); }
        else if (name === "error") { finished = true; onError(new ApiError(d.code, d.message, 200, !!d.needs_key), d.step); }
      }
    }
    if (!finished) onError(new ApiError("NETWORK", "The connection ended before your page was finished. Please try again.", 0));
  } catch (e) {
    if (e.name !== "AbortError") onError(new ApiError("NETWORK", "The connection was interrupted. Please try again.", 0));
  }
}

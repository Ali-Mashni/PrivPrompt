// extension/injected.js
(function () {
  // mark main-world load
  try {
    console.debug("[PrivPrompt] injected.js loaded");
    document.documentElement.setAttribute("data-ppf-injected", "1");
  } catch {}

  const PPF_DEBUG_ALL = true; // set to false after you confirm logs

  function toast(msg) {
    let el = document.getElementById("ppf-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "ppf-toast";
      el.style.cssText =
        "position:fixed;right:16px;bottom:16px;z-index:2147483647;max-width:380px;padding:10px 12px;border-radius:8px;background:rgba(20,20,20,.9);color:#fff;font:13px/1.4 sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.25);pointer-events:none;opacity:0;transform:translateY(12px);transition:all .25s;";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.opacity = "1";
    el.style.transform = "translateY(0)";
    clearTimeout(el._t);
    el._t = setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(12px)";
    }, 2200);
  }

  function looksJson(s) {
    if (typeof s !== "string") return false;
    const t = s.trim();
    return (t.startsWith("{") && t.endsWith("}")) || (t.startsWith("[") && t.endsWith("]"));
  }

  function askProxy(payload) {
    return new Promise((resolve) => {
      const id = Math.random().toString(36).slice(2);
      function onReply(evt) {
        const d = evt.data;
        if (!d || d.__ppf !== "FROM_EXTENSION" || d.id !== id) return;
        window.removeEventListener("message", onReply);
        resolve(d.decision || { action: "allow" });
      }
      window.addEventListener("message", onReply);
      window.postMessage({ __ppf: "FROM_PAGE", id, payload }, "*");
      setTimeout(() => { window.removeEventListener("message", onReply); resolve({ action: "allow" }); }, 1500);
    });
  }

  // ---- patch fetch (handles Request objects) ----
const _fetch = window.fetch;
window.fetch = async function (input, init = {}) {
  // Normalize to url + method
  const isReq = (typeof Request !== "undefined") && (input instanceof Request);
  const url = isReq ? input.url : (typeof input === "string" ? input : (input && input.url) || "");
  const method = (init?.method || (isReq ? input.method : (typeof input !== "string" && input?.method)) || "GET").toUpperCase();

  // Only inspect ChatGPT requests
  const shouldInspect = url.includes("chatgpt.com");
  if (!shouldInspect) return _fetch.call(this, input, init);

  // Try to read the body (works when the body isn't a stream already consumed)
  let bodyText = null, bodyKind = "none";
  let headersFromReq = null;

  try {
    if (isReq) {
      headersFromReq = new Headers(input.headers); // keep headers for rebuild
      // If body exists and hasn't been used, read it
      if (!input.bodyUsed && method !== "GET" && method !== "HEAD") {
        try {
          bodyText = await input.clone().text();       // <— key fix
          const t = bodyText.trim();
          bodyKind = (t.startsWith("{") || t.startsWith("[")) ? "json" : "text";
        } catch {
          bodyKind = "unknown";
        }
      }
    } else if (init && "body" in init && init.body != null) {
      if (typeof init.body === "string") {
        bodyText = init.body;
        const t = bodyText.trim();
        bodyKind = (t.startsWith("{") || t.startsWith("[")) ? "json" : "text";
      } else if (init.body instanceof FormData) bodyKind = "multipart";
      else if (init.body instanceof Blob) bodyKind = "binary";
      else { try { bodyText = init.body.toString(); bodyKind = "text"; } catch { bodyKind = "unknown"; } }
    }
  } catch {
    // ignore read errors; we’ll fail-open
  }

  // Ask proxy for a decision
  let decision = { action: "allow" };
  try {
    decision = await (new Promise((resolve) => {
      const id = Math.random().toString(36).slice(2);
      function onReply(evt) {
        const d = evt.data;
        if (!d || d.__ppf !== "FROM_EXTENSION" || d.id !== id) return;
        window.removeEventListener("message", onReply);
        resolve(d.decision || { action: "allow" });
      }
      window.addEventListener("message", onReply);
      window.postMessage({ __ppf: "FROM_PAGE", id, payload: { context: "fetch", url, method, bodyKind, body: bodyText } }, "*");
      setTimeout(() => { window.removeEventListener("message", onReply); resolve({ action: "allow" }); }, 1500);
    }));
  } catch {}

  // Apply decision
  if (decision?.action === "block") {
    // behave like a network failure
    throw new Error("PrivPrompt blocked request");
  }

  if (decision?.action === "modify" && typeof decision.body === "string") {
    // Rebuild the request with sanitized body
    if (isReq) {
      const opts = {
        method,
        headers: headersFromReq ? new Headers(headersFromReq) : undefined,
        body: decision.body,
        // copy key flags to keep behavior the same
        mode: input.mode,
        credentials: input.credentials,
        cache: input.cache,
        redirect: input.redirect,
        referrer: input.referrer,
        referrerPolicy: input.referrerPolicy,
        integrity: input.integrity,
        keepalive: input.keepalive
      };
      // Ensure content-type is set for JSON strings
      if (decision.body && opts.headers && !opts.headers.has("content-type")) {
        if (decision.body.trim().startsWith("{") || decision.body.trim().startsWith("[")) {
          opts.headers.set("content-type", "application/json");
        }
      }
      const newReq = new Request(url, opts);
      return _fetch.call(this, newReq);
    } else {
      init = init || {};
      init.body = decision.body;
      if (!init.headers) init.headers = {};
      if (decision.body.trim().startsWith("{") || decision.body.trim().startsWith("[")) {
        if (init.headers instanceof Headers) {
          if (!init.headers.has("content-type")) init.headers.set("content-type", "application/json");
        } else if (typeof init.headers === "object" && !("content-type" in init.headers)) {
          init.headers["content-type"] = "application/json";
        }
      }
      return _fetch.call(this, input, init);
    }
  }

  // Default: let it through
  return _fetch.call(this, input, init);
};

})();

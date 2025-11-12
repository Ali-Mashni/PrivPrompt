// extension/injected.js
(function () {
  // (Optional) mark main-world load without logging
  try { document.documentElement.setAttribute("data-ppf-injected", "1"); } catch {}

  // -- UI toast -----------------------------------------------------
  function toast(msg) {
  let el = document.getElementById("ppf-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "ppf-toast";
    el.style.cssText = [
      "position:fixed",
      "right:20px",
      "bottom:20px",
      "z-index:2147483647",
      "max-width:460px",
      "padding:14px 16px",
      "border-radius:10px",
      "background:rgba(20,20,20,.92)",
      "color:#fff",
      "font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif",
      "box-shadow:0 10px 28px rgba(0,0,0,.35)",
      "pointer-events:none",
      "opacity:0",
      "transform:translateY(14px) scale(0.98)",
      "transition:opacity .25s ease, transform .25s ease",
      "border:1px solid rgba(255,255,255,.08)"
    ].join(";");
    document.body.appendChild(el);
  }

  el.textContent = msg;

  // show
  el.style.opacity = "1";
  el.style.transform = "translateY(0) scale(1)";

  // stays for (4.5s)
  const HOLD_MS = 4500;

  // clear any previous hide timer
  clearTimeout(el._t);

  el._t = setTimeout(() => {
    // hide
    el.style.opacity = "0";
    el.style.transform = "translateY(14px) scale(0.98)";
  }, HOLD_MS);
}


  // -- helpers ----------------------------------------------------------------
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
      // fail-open if no decision comes back quickly
      setTimeout(() => {
        window.removeEventListener("message", onReply);
        resolve({ action: "allow" });
      }, 1500);
    });
  }

  // Only inspect actual message POSTs to ChatGPT (anonymous; extend if needed)
  function shouldInspectUrl(url) {
    return /https:\/\/chatgpt\.com\/backend-anon\/f\/conversation\b/.test(url);
  }

  // -- patch fetch -------------------------------------------------------------
  const _fetch = window.fetch;
  window.fetch = async function (input, init = {}) {
    const isReq = (typeof Request !== "undefined") && (input instanceof Request);
    const url = isReq ? input.url : (typeof input === "string" ? input : (input && input.url) || "");
    const method = (
      init?.method ||
      (isReq ? input.method : (typeof input !== "string" && input?.method)) ||
      "GET"
    ).toUpperCase();

    // Only touch the requests we care about
    if (!shouldInspectUrl(url)) {
      return _fetch.call(this, input, init);
    }

    // Try to read request body (non-destructively)
    let bodyText = null, bodyKind = "none";
    let headersFromReq = null;
    try {
      if (isReq) {
        headersFromReq = new Headers(input.headers);
        if (!input.bodyUsed && method !== "GET" && method !== "HEAD") {
          try {
            bodyText = await input.clone().text();
            bodyKind = looksJson(bodyText) ? "json" : "text";
          } catch { bodyKind = "unknown"; }
        }
      } else if (init && "body" in init && init.body != null) {
        if (typeof init.body === "string") {
          bodyText = init.body;
          bodyKind = looksJson(bodyText) ? "json" : "text";
        } else if (init.body instanceof FormData) {
          bodyKind = "multipart";
        } else if (init.body instanceof Blob) {
          bodyKind = "binary";
        } else {
          try { bodyText = init.body.toString(); bodyKind = "text"; }
          catch { bodyKind = "unknown"; }
        }
      }
    } catch {
      // fail-open on read errors
    }

    // Ask the extension/proxy for a decision
    let decision = { action: "allow" };
    try {
      decision = await askProxy({ context: "fetch", url, method, bodyKind, body: bodyText });
    } catch { /* fail-open */ }

    if (decision?.notify?.message) {
      toast(decision.notify.message);
    }

    if (decision?.action === "block") {
      toast("PrivPrompt: blocked request");
      throw new Error("PrivPrompt blocked request");
    }

    if (decision?.action === "modify" && typeof decision.body === "string") {
      toast("PrivPrompt: sanitized request");
      // Rebuild the request with the sanitized body
      if (isReq) {
        const opts = {
          method,
          headers: headersFromReq ? new Headers(headersFromReq) : undefined,
          body: decision.body,
          mode: input.mode,
          credentials: input.credentials,
          cache: input.cache,
          redirect: input.redirect,
          referrer: input.referrer,
          referrerPolicy: input.referrerPolicy,
          integrity: input.integrity,
          keepalive: input.keepalive
        };
        // Ensure content-type is present for JSON
        if (decision.body && opts.headers && !opts.headers.has("content-type")) {
          if (looksJson(decision.body)) opts.headers.set("content-type", "application/json");
        }
        const newReq = new Request(url, opts);
        return _fetch.call(this, newReq);
      } else {
        init = init || {};
        init.body = decision.body;
        if (!init.headers) init.headers = {};
        const isJson = looksJson(decision.body);
        if (isJson) {
          if (init.headers instanceof Headers) {
            if (!init.headers.has("content-type")) init.headers.set("content-type", "application/json");
          } else if (typeof init.headers === "object" && !("content-type" in init.headers)) {
            init.headers["content-type"] = "application/json";
          }
        }
        return _fetch.call(this, input, init);
      }
    }

    // Default pass-through
    return _fetch.call(this, input, init);
  };
})();

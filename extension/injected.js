(function () {
  // ------------- toast (waits for body) -------------
  function ensureBody(cb) {
    if (document.body) return cb();
    const i = setInterval(() => {
      if (document.body) { clearInterval(i); cb(); }
    }, 10);
  }

  function toast(msg) {
    ensureBody(() => {
      let el = document.getElementById("ppf-toast");
      if (!el) {
        el = document.createElement("div");
        el.id = "ppf-toast";
        el.style.cssText = [
          "position:fixed","right:20px","bottom:20px","z-index:2147483647",
          "max-width:520px","padding:16px 18px","border-radius:12px",
          "background:rgba(20,20,20,.94)","color:#fff",
          "font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif",
          "box-shadow:0 14px 36px rgba(0,0,0,.38)","pointer-events:none",
          "opacity:0","transform:translateY(16px) scale(.98)",
          "transition:opacity .28s ease, transform .28s ease",
          "border:1px solid rgba(255,255,255,.08)"
        ].join(";");
        document.body.appendChild(el);
      }
      el.textContent = msg;
      el.style.opacity = "1";
      el.style.transform = "translateY(0) scale(1)";
      clearTimeout(el._t);
      el._t = setTimeout(() => {
        el.style.opacity = "0";
        el.style.transform = "translateY(16px) scale(.98)";
      }, 5500);
    });
  }

  // ------------- helpers -------------
  function looksJson(s) {
    if (typeof s !== "string") return false;
    const t = s.trim();
    return (t.startsWith("{") && t.endsWith("}")) || (t.startsWith("[") && t.endsWith("]"));
  }
  // --- per-send correlation (reuse within a short window) ---
  const _ppfSend = { lastId: null, lastAt: 0 };
  function newSendId() { return Math.random().toString(36).slice(2); }

  function sendIdFor(url) {
    // We don't really need the URL to key; ChatGPT fires the twin POSTs within ~500ms
    const now = Date.now();
    if (now - _ppfSend.lastAt < 600) { // reuse if within 600ms
      _ppfSend.lastAt = now;
      return _ppfSend.lastId || (_ppfSend.lastId = newSendId());
    }
    _ppfSend.lastAt = now;
    _ppfSend.lastId = newSendId();
    return _ppfSend.lastId;
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

  // Logged-in & logged-out conversation endpoints
  function shouldInspect(url, method = "GET") {
  if (String(method).toUpperCase() !== "POST") return false;
  return /^https:\/\/chatgpt\.com\/(backend-api|backend-anon)\/(?:f\/)?conversation(?:\?.*)?$/.test(url);
  }


  // ========== FETCH PATCH (re-patchable) ==========
  (function patchFetch() {
    if (!window.fetch) return;
    if (window.fetch.__ppfWrapped) return;  // don’t double-wrap
    const _fetch = window.fetch;

    async function wrappedFetch(input, init = {}) {
      const isReq = (typeof Request !== "undefined") && (input instanceof Request);
      const url = isReq ? input.url : (typeof input === "string" ? input : (input && input.url) || "");
      const method = (
        init?.method ||
        (isReq ? input.method : (typeof input !== "string" && input?.method)) ||
        "GET"
      ).toUpperCase();

      if (!shouldInspect(url, method)) return _fetch.call(this, input, init);

      let bodyText = null, bodyKind = "none";
      let headersFromReq = null;
      try {
        if (isReq) {
          headersFromReq = new Headers(input.headers);
          if (!input.bodyUsed && method !== "GET" && method !== "HEAD") {
            try { bodyText = await input.clone().text(); bodyKind = looksJson(bodyText) ? "json" : "text"; }
            catch { bodyKind = "unknown"; }
          }
        } else if (init && "body" in init && init.body != null) {
          if (typeof init.body === "string") { bodyText = init.body; bodyKind = looksJson(bodyText) ? "json" : "text"; }
          else if (init.body instanceof FormData) bodyKind = "multipart";
          else if (init.body instanceof Blob) bodyKind = "binary";
          else { try { bodyText = init.body.toString(); bodyKind = "text"; } catch { bodyKind = "unknown"; } }
        }
      } catch {}

      const sendId = sendIdFor(url);
      const decision = await askProxy({
        context: "fetch",
        url,
        method,
        bodyKind,
        body: bodyText,
        sendId
        }).catch(() => ({ action: "allow" }));


      if (decision?.notify?.message) toast(decision.notify.message);
      if (decision?.action === "block") { toast("PrivPrompt: blocked request"); throw new Error("PrivPrompt blocked request"); }

      if (decision?.action === "modify" && typeof decision.body === "string") {
        toast("PrivPrompt: sanitized request");
        if (isReq) {
          const opts = {
            method,
            headers: headersFromReq ? new Headers(headersFromReq) : undefined,
            body: decision.body,
            mode: input.mode, credentials: input.credentials, cache: input.cache,
            redirect: input.redirect, referrer: input.referrer, referrerPolicy: input.referrerPolicy,
            integrity: input.integrity, keepalive: input.keepalive
          };
          if (opts.headers && !opts.headers.has("content-type") && looksJson(decision.body)) {
            opts.headers.set("content-type", "application/json");
          }
          const newReq = new Request(url, opts);
          return _fetch.call(this, newReq);
        } else {
          init = init || {};
          init.body = decision.body;
          if (!init.headers) init.headers = {};
          if (looksJson(decision.body)) {
            if (init.headers instanceof Headers) {
              if (!init.headers.has("content-type")) init.headers.set("content-type", "application/json");
            } else if (typeof init.headers === "object" && !("content-type" in init.headers)) {
              init.headers["content-type"] = "application/json";
            }
          }
          return _fetch.call(this, input, init);
        }
      }

      return _fetch.call(this, input, init);
    }

    wrappedFetch.__ppfWrapped = true;
    window.fetch = wrappedFetch;
  })();

  // ========== XHR PATCH (re-patchable) ==========
  (function patchXHR() {
    if (!window.XMLHttpRequest) return;
    if (XMLHttpRequest.prototype.__ppfWrapped) return;

    const _open = XMLHttpRequest.prototype.open;
    const _send = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      this.__ppf = { method: String(method || "GET").toUpperCase(), url: String(url || "") };
      return _open.call(this, method, url, ...rest);
    };

    XMLHttpRequest.prototype.send = async function (body) {
      const info = this.__ppf || { method: "GET", url: "" };
      if (!shouldInspect(info.url, info.method)) return _send.call(this, body);

      let bodyKind = "none", bodyText = null;
      if (typeof body === "string") { bodyText = body; bodyKind = looksJson(body) ? "json" : "text"; }
      else if (body instanceof FormData) bodyKind = "multipart";
      else if (body instanceof Blob) bodyKind = "binary";

      const decision = await askProxy({ context: "xhr", url: info.url, method: info.method, bodyKind, body: bodyText }).catch(() => ({ action: "allow" }));

      if (decision?.notify?.message) toast(decision.notify.message);
      if (decision?.action === "block") { toast("PrivPrompt: blocked request"); try { this.abort(); } catch {} return; }
      if (decision?.action === "modify" && typeof decision.body === "string") { body = decision.body; toast("PrivPrompt: sanitized request"); }

      return _send.call(this, body);
    };

    XMLHttpRequest.prototype.__ppfWrapped = true;
  })();

  // ========== sendBeacon PATCH (optional) ==========
  // ========== sendBeacon PATCH (optional) ==========
(function patchBeacon() {
  const orig = navigator.sendBeacon?.bind(navigator);
  if (!orig || navigator.sendBeacon.__ppfWrapped) return;

  function wrapped(url, data) {
    const u = String(url || "");
    // sendBeacon => POST
    if (!shouldInspect(u, "POST")) return orig(url, data);

    let bodyKind = "none", bodyText = null;
    if (typeof data === "string") { bodyText = data; bodyKind = looksJson(data) ? "json" : "text"; }
    else if (data instanceof Blob) bodyKind = "binary";
    else if (data instanceof FormData) bodyKind = "multipart";

    askProxy({ context: "beacon", url: u, method: "POST", bodyKind, body: bodyText })
      .then(decision => { if (decision?.notify?.message) toast(decision.notify.message); })
      .catch(() => {});
    return orig(url, data);
  }

  wrapped.__ppfWrapped = true;
  navigator.sendBeacon = wrapped;
})();
})();

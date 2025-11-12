// mark page when content script runs (optional)
try { document.documentElement.setAttribute("data-ppf-content", "1"); } catch {}

// (optional) inject toast.css
try {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = chrome.runtime.getURL("toast.css");
  (document.head || document.documentElement).appendChild(link);
} catch {}

// --- main-world injector + SPA re-injection (no blocking sentinel) ---
(function () {
  function inject() {
    const s = document.createElement("script");
    s.src = chrome.runtime.getURL("injected.js");
    s.async = false;
    (document.head || document.documentElement).appendChild(s);
    s.onload = () => s.remove();
  }

  // inject ASAP
  inject();

  // re-inject on SPA route changes & tab visibility
  const _push = history.pushState;
  const _replace = history.replaceState;
  history.pushState = function (...args) { const r = _push.apply(this, args); queueMicrotask(inject); return r; };
  history.replaceState = function (...args) { const r = _replace.apply(this, args); queueMicrotask(inject); return r; };
  window.addEventListener("popstate", () => queueMicrotask(inject));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") queueMicrotask(inject);
  });
})();

// ---- BRIDGE: page -> service worker -> proxy -> back ----
window.addEventListener("message", (evt) => {
  if (evt.source !== window) return;
  const data = evt.data;
  if (!data || data.__ppf !== "FROM_PAGE") return;

  chrome.runtime.sendMessage(
    { type: "PPF_INSPECT", payload: data.payload },
    (decision) => {
      if (chrome.runtime.lastError || !decision) {
        decision = { action: "allow" };
      }
      window.postMessage({ __ppf: "FROM_EXTENSION", id: data.id, decision }, "*");
    }
  );
});

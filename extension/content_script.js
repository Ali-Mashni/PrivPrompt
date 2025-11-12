// extension/content_script.js

// mark page when content script runs (optional)
try { document.documentElement.setAttribute("data-ppf-content", "1"); } catch {}

// (optional) inject toast.css if you have one; injected.js already uses inline styles
try {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = chrome.runtime.getURL("toast.css");
  (document.head || document.documentElement).appendChild(link);
} catch {}

// inject the main-world script so it can patch window.fetch
try {
  const s = document.createElement("script");
  s.src = chrome.runtime.getURL("injected.js");
  s.async = false;
  (document.head || document.documentElement).appendChild(s);
  s.onload = () => s.remove();
} catch {}

// ---- BRIDGE: page -> service worker -> proxy -> back ----
window.addEventListener("message", (evt) => {
  // only accept messages from the same page context
  if (evt.source !== window) return;
  const data = evt.data;
  if (!data || data.__ppf !== "FROM_PAGE") return;

  // use callback-style to be compatible with all Chrome versions
  chrome.runtime.sendMessage(
    { type: "PPF_INSPECT", payload: data.payload },
    (decision) => {
      // if the service worker errored or returned nothing, fail-open
      if (chrome.runtime.lastError || !decision) {
        decision = { action: "allow" };
      }
      window.postMessage(
        { __ppf: "FROM_EXTENSION", id: data.id, decision },
        "*"
      );
    }
  );
});

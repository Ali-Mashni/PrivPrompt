// service_worker.js

// Ensure a default mode exists on first install
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get({ ppf_mode: null }, ({ ppf_mode }) => {
    if (!ppf_mode) chrome.storage.local.set({ ppf_mode: "warn" });
  });
});

// Relay inspection to local proxy; include current mode
async function ppfInspect(payload) {
  // read mode fresh so popup changes take effect immediately
  const { ppf_mode } = await chrome.storage.local.get({ ppf_mode: "warn" });

  // Add a short timeout so messages don't hang if proxy is down
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 1500);

  try {
    const res = await fetch("http://localhost:8787/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, mode: ppf_mode }),
      signal: ctrl.signal
    });
    clearTimeout(to);
    return await res.json();
  } catch (e) {
    clearTimeout(to);
    // fail-open
    return { action: "allow" };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "PPF_INSPECT") {
    const enriched = { ...msg.payload, tabId: sender?.tab?.id ?? null }
    ppfInspect(enriched).then(sendResponse);
    return true; // async
  }
  if (msg?.type === "PPF_SET_MODE") {
    // popup writes to storage; we just ACK
    sendResponse({ ok: true });
  }
});

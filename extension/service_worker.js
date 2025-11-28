// service_worker.js

// Ensure a default mode exists on first install
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get({ ppf_mode: "warn" }).then(({ ppf_mode }) => {
    if (!ppf_mode) {
      chrome.storage.local.set({ ppf_mode: "warn" });
    }
  }).catch(err => {
    console.error("[PPF] onInstalled storage init failed:", err);
  });
});


// Relay inspection to local proxy; include current mode
async function ppfInspect(payload) {
  let ppf_mode = "warn";

  // Read mode from storage, but don't crash if it fails
  try {
    const res = await chrome.storage.local.get({ ppf_mode: "warn" });
    ppf_mode = res.ppf_mode || "warn";
  } catch (e) {
    console.error("[PPF] storage.get failed, using default mode 'warn':", e);
  }

  // Short timeout so we don't hang if the proxy is down
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
    console.warn("[PPF] proxy fetch failed, allowing request:", e);
    // fail-open
    return { action: "allow" };
  }
}


chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "PPF_INSPECT") {
    (async () => {
      try {
        const enriched = { ...msg.payload, tabId: sender?.tab?.id ?? null };
        const decision = await ppfInspect(enriched);
        sendResponse(decision || { action: "allow" });
      } catch (err) {
        console.error("[PPF] ppfInspect handler crashed, allowing:", err);
        sendResponse({ action: "allow" });
      }
    })();
    return true; // async
  }

  if (msg?.type === "PPF_SET_MODE") {
    try {
      sendResponse({ ok: true });
    } catch (err) {
      console.error("[PPF] failed to ACK PPF_SET_MODE:", err);
    }
  }
});


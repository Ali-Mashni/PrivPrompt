// Relay inspection to local proxy; include current mode
async function ppfInspect(payload) {
  // read mode fresh so popup changes take effect immediately
  const { ppf_mode } = await chrome.storage.local.get({ ppf_mode: "warn" });
  const res = await fetch("http://localhost:8787/inspect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, mode: ppf_mode })
  });
  return res.json();
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "PPF_INSPECT") {
    ppfInspect(msg.payload).then(sendResponse).catch(() => sendResponse({ action: "allow" }));
    return true;
  }
  if (msg?.type === "PPF_SET_MODE") {
    // nothing else to do; popup already stored it
    sendResponse({ ok: true });
  }
});

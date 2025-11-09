const toggle = document.getElementById('toggle');
const statusEl = document.getElementById('status');

chrome.storage.session.get("pp_private", ({ pp_private }) => {
  toggle.checked = Boolean(pp_private);
  statusEl.textContent = toggle.checked ? "Active" : "Off";
});

toggle.addEventListener('change', async () => {
  const active = toggle.checked;
  chrome.storage.session.set({ pp_private: active });
  statusEl.textContent = active ? "Active" : "Off";

  // Clear cookies/storage for AI domain on start and end
  try {
    await chrome.browsingData.remove({origins:["https://api.openai.com"]}, {
      cookies: true, localStorage: true, indexedDB: true, cacheStorage: true
    });
  } catch(e) {}

  // Tell the proxy to rotate session salt
  try {
    await fetch("http://localhost:8787/session/start", { method: "POST" });
  } catch(e) {}
});

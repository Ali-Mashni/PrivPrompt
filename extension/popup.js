const sel = document.getElementById("mode");
const statusEl = document.getElementById("status");

const setStatus = (t) => statusEl.textContent = t;

chrome.storage.local.get(["ppf_mode"], ({ ppf_mode }) => {
  sel.value = ppf_mode || "warn";
  setStatus(`Current mode: ${sel.value}`);
});

sel.addEventListener("change", () => {
  const mode = sel.value;
  chrome.storage.local.set({ ppf_mode: mode }, () => {
    chrome.runtime.sendMessage({ type: "PPF_SET_MODE", mode }, (res) => {
      setStatus(res?.ok ? `Current mode: ${mode}` : "Failed to set mode");
    });
  });
});

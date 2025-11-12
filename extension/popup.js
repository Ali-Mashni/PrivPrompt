// popup.js
const MODE_KEY = "ppf_mode";
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function setActive(mode){
  $$(".seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
}

async function loadMode(){
  const obj = await chrome.storage.local.get({ [MODE_KEY]: "warn" });
  return obj[MODE_KEY] || "warn";
}

async function saveMode(mode){
  await chrome.storage.local.set({ [MODE_KEY]: mode });
  // Optional: tell the worker (not strictly required since worker reads fresh per request)
  chrome.runtime.sendMessage({ type: "PPF_SET_MODE", mode }).catch(()=>{});
}

async function healthCheck(){
  const dot = $("#dot");
  const st  = $("#statusText");
  try{
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const r = await fetch("http://localhost:8787/healthz", { signal: ctrl.signal });
    clearTimeout(t);
    if (r.ok){
      dot.classList.remove("bad"); dot.classList.add("ok");
      st.textContent = "Proxy: healthy";
      return true;
    }
    throw new Error("non-200");
  }catch{
    dot.classList.remove("ok"); dot.classList.add("bad");
    st.textContent = "Proxy: unreachable";
    return false;
  }
}

(async function init(){
  const current = await loadMode();
  setActive(current);

  $$(".seg button").forEach(b=>{
    b.addEventListener("click", ()=> setActive(b.dataset.mode));
  });

  $("#btnSave").addEventListener("click", async ()=>{
    const active = $$(".seg button").find(b => b.getAttribute("aria-pressed") === "true").dataset.mode;
    await saveMode(active);
    $("#statusText").textContent = `Saved: ${active}`;
  });

  $("#btnHealth").addEventListener("click", healthCheck);
  healthCheck();
})();

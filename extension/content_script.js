// mark page when content script runs
try { document.documentElement.setAttribute("data-ppf-content", "1"); } catch {}

// inject toast css
const link = document.createElement("link");
link.rel = "stylesheet";
link.href = chrome.runtime.getURL("toast.css");
(document.head || document.documentElement).appendChild(link);

// inject main-world script
const s = document.createElement("script");
s.src = chrome.runtime.getURL("injected.js");
s.async = false;
(document.head || document.documentElement).appendChild(s);
s.onload = () => s.remove();

// bridge: page -> service worker -> proxy -> back
window.addEventListener("message", async (evt) => {
  const data = evt.data;
  if (!data || data.__ppf !== "FROM_PAGE") return;

  try {
    const decision = await chrome.runtime.sendMessage({
      type: "PPF_INSPECT",
      payload: data.payload
    });
    window.postMessage({ __ppf: "FROM_EXTENSION", id: data.id, decision }, "*");
  } catch {
    window.postMessage({ __ppf: "FROM_EXTENSION", id: data.id, decision: { action: "allow" } }, "*");
  }
});

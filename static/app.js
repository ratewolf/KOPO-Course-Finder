// Pinned browser module: no package installation or build step is required.
const CLIENT_URL = "https://cdn.jsdelivr.net/npm/@gradio/client@1.17.0/dist/index.min.js";
const $ = (id) => document.getElementById(id);
let client = null;
let busy = false;
let generation = 0;

async function deadline(promise, milliseconds) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("Request timed out")), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}

function controls() {
  document.querySelectorAll("[data-online]").forEach((el) => { el.disabled = !client || busy; });
  $("key").disabled = !client || busy;
  $("question").disabled = !client || busy;
  $("connect").disabled = busy || !!client;
  $("server").disabled = busy || !!client;
  $("disconnect").disabled = busy || !client;
}
function serverURL(value) {
  const url = new URL(value.trim());
  if (url.username || url.password || url.search || url.hash) throw new Error("주소 형식");
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) throw new Error("HTTPS 필요");
  return url.href.replace(/\/$/, "");
}
function clearResult() {
  for (const id of ["original", "rewritten", "sql", "table", "history"]) $(id).replaceChildren();
  $("status").textContent = "준비";
  $("message").textContent = "질문을 입력해 주세요.";
}
function render(data) {
  const [history, message, original, rewritten, frame, sql, status] = data;
  for (const [id, value] of Object.entries({message, original, rewritten, sql, status})) {
    if (typeof value === "string") $(id).textContent = value;
  }
  if (frame && Array.isArray(frame.headers) && Array.isArray(frame.data)) {
    $("table").replaceChildren();
    const head = document.createElement("thead");
    const row = document.createElement("tr");
    for (const label of frame.headers) { const cell = document.createElement("th"); cell.textContent = String(label); row.append(cell); }
    head.append(row); $("table").append(head);
    const body = document.createElement("tbody");
    for (const values of frame.data) { const tr = document.createElement("tr"); for (const value of values) { const td = document.createElement("td"); td.textContent = value == null ? "" : String(value); tr.append(td); } body.append(tr); }
    $("table").append(body);
  }
  if (Array.isArray(history)) {
    $("history").replaceChildren();
    for (const item of history) {
      if (typeof item.content !== "string") continue;
      const p = document.createElement("p"); p.textContent = `${item.role === "user" ? "질문" : "안내"}: ${item.content}`; $("history").append(p);
    }
  }
}
$("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (busy || client) return;
  let url;
  try { url = serverURL($("server").value); }
  catch { $("connection").textContent = "HTTPS 주소 또는 http://127.0.0.1:7860 같은 로컬 주소를 입력해 주세요. 계정·키·쿼리 문자열은 주소에 넣지 마세요."; return; }
  $("direct").href = url;
  busy = true; controls(); $("connection").textContent = "조회 서버에 연결하고 있습니다…";
  let expired = false;
  let candidate = null;
  try {
    const pending = (async () => {
      const { Client } = await import(CLIENT_URL);
      const connected = await Client.connect(url);
      candidate = connected;
      if (expired) { connected.close(); throw new Error("Connection expired"); }
      const api = await connected.view_api();
      if (expired || !api.named_endpoints["/query"]) { connected.close(); throw new Error("API mismatch"); }
      return connected;
    })();
    const connected = await deadline(pending, 20000);
    client = connected; generation++; clearResult();
    $("connection").textContent = `조회 시스템 연결 · ${url}`;
  } catch {
    expired = true; candidate?.close();
    $("connection").textContent = "조회 서버에 연결할 수 없거나 20초 안에 응답하지 않았습니다. 서버 실행·주소·CORS·로컬 네트워크 접근 권한을 확인해 주세요. 차단되면 아래 직접 접속 링크를 이용하세요.";
  } finally { busy = false; controls(); }
});
$("disconnect").addEventListener("click", async () => {
  if (!client || busy) return;
  busy = true; controls();
  try { await deadline(client.predict("/release_key", []), 10000); } catch { /* Server TTL remains the fallback. */ }
  client.close(); client = null; generation++; $("key").value = ""; clearResult();
  $("key-status").textContent = "연결을 해제했습니다. 새 연결에는 키를 다시 적용해 주세요.";
  $("connection").textContent = "연결을 해제했습니다."; busy = false; controls();
});
$("query-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!client || busy || !$("question").value.trim()) return;
  busy = true; controls(); const current = generation; $("status").textContent = "조회 중…";
  try {
    const response = await client.predict("/query", [$("question").value.trim(), $("new-query").checked]);
    if (current === generation) render(response.data);
  } catch { $("status").textContent = "연결 또는 조회 오류"; $("message").textContent = "조회가 완료되지 않았습니다. 서버 상태를 확인한 뒤 다시 시도해 주세요. 기존 표가 있다면 이전 결과입니다."; }
  finally { busy = false; controls(); }
});
async function action(endpoint, args, isKey = false) {
  if (!client || busy) return;
  busy = true; controls();
  try {
    const response = await client.predict(endpoint, args);
    if (isKey) $("key-status").textContent = response.data[1];
    else { clearResult(); $("question").value = ""; $("new-query").checked = false; $("message").textContent = "대화와 결과를 초기화했습니다."; }
  } catch { $(isKey ? "key-status" : "status").textContent = "요청에 실패했습니다. 서버 연결 및 앱 버전을 확인해 주세요."; }
  finally { $("key").value = ""; busy = false; controls(); }
}
$("apply-key").addEventListener("click", () => { const key = $("key").value.trim(); $("key").value = ""; if (key) action("/set_key", [key], true); });
$("release-key").addEventListener("click", () => action("/release_key", [], true));
$("reset").addEventListener("click", () => action("/reset", []));
document.querySelectorAll("[data-example]").forEach((button) => button.addEventListener("click", () => { if (!busy) $("question").value = button.dataset.example; }));
window.addEventListener("pagehide", () => { $("key").value = ""; client?.close(); });

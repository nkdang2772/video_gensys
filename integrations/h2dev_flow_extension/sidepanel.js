// ============================================================
//  Flow Batch — sidepanel.js
//  Điều phối: đọc prompt -> gửi từng cái cho content.js trên
//  tab Flow -> nhận ảnh -> tải về -> nghỉ ngẫu nhiên -> lặp.
// ============================================================

const $ = (id) => document.getElementById(id);
const els = {
  prompts: $("prompts"),
  count: $("count"),
  loadTxt: $("loadTxt"),
  txtFile: $("txtFile"),
  folder: $("folder"),
  serial: $("serial"),
  delayMin: $("delayMin"),
  delayMax: $("delayMax"),
  start: $("start"),
  stop: $("stop"),
  queue: $("queue"),
  progress: $("progress"),
  pfill: $("pfill"),
  conn: $("conn"),
  connText: $("connText"),
  bridgeEnabled: $("bridgeEnabled"),
  bridgeUrl: $("bridgeUrl"),
  bridgeToken: $("bridgeToken"),
  bridgeStatus: $("bridgeStatus"),
};

let running = false;
let items = []; // [{prompt, status}]
let bridgeBusy = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- Lưu / khôi phục cài đặt ----------
function saveSettings() {
  chrome.storage.local.set({
    prompts: els.prompts.value,
    folder: els.folder.value,
    serial: els.serial.checked,
    delayMin: els.delayMin.value,
    delayMax: els.delayMax.value,
    bridgeEnabled: els.bridgeEnabled.checked,
    bridgeUrl: els.bridgeUrl.value,
    bridgeToken: els.bridgeToken.value,
  });
}
async function loadSettings() {
  const s = await chrome.storage.local.get();
  if (s.prompts != null) els.prompts.value = s.prompts;
  if (s.folder) els.folder.value = s.folder;
  if (s.serial != null) els.serial.checked = s.serial;
  if (s.delayMin != null) els.delayMin.value = s.delayMin;
  if (s.delayMax != null) els.delayMax.value = s.delayMax;
  if (s.bridgeEnabled != null) els.bridgeEnabled.checked = s.bridgeEnabled;
  if (s.bridgeUrl) els.bridgeUrl.value = s.bridgeUrl;
  if (s.bridgeToken) els.bridgeToken.value = s.bridgeToken;
  refreshCount();
}

// ---------- Đếm prompt ----------
function parsePrompts() {
  return els.prompts.value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}
function refreshCount() {
  els.count.textContent = `${parsePrompts().length} prompt`;
}

// ---------- Tìm tab Google Flow ----------
async function getFlowTab() {
  // URL có thể là /fx/tools/flow HOẶC /fx/vi/tools/flow (kèm mã ngôn ngữ)
  const tabs = await chrome.tabs.query({ url: "https://labs.google/fx/*" });
  return tabs.find((t) => /\/tools\/flow/.test(t.url || "")) || null;
}

// ---------- Gửi tin nhắn tới content script ----------
function sendToTab(tabId, msg) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (resp) => {
      if (chrome.runtime.lastError) resolve(null);
      else resolve(resp);
    });
  });
}

// gửi cho background (nơi điều khiển chrome.debugger)
function sendToBg(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (resp) => {
      if (chrome.runtime.lastError) resolve(null);
      else resolve(resp);
    });
  });
}

// ---------- Kiểm tra kết nối ----------
async function checkConnection() {
  const tab = await getFlowTab();
  if (!tab) return setConn(false, "Hãy mở một project Google Flow");

  // thử ping
  let resp = await sendToTab(tab.id, { type: "PING" });

  // không thấy content script -> tự tiêm lại rồi ping lần nữa (tự chữa)
  if (!resp) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"],
      });
      await new Promise((r) => setTimeout(r, 400));
      resp = await sendToTab(tab.id, { type: "PING" });
    } catch (e) {
      console.warn("[h2dev_flow] Không tiêm được content script:", e);
    }
  }

  if (!resp) return setConn(false, "Tải lại trang Flow (F5) rồi thử lại");
  // PING ok => coi như đã kết nối (lúc chạy bot sẽ focus để ô prompt hiện ra)
  if (resp.hasInput) setConn(true, "Đã kết nối với Google Flow");
  else setConn(true, "Đã kết nối (ô prompt sẽ nhận diện khi chạy)");
  return tab;
}
function setConn(on, text) {
  els.conn.className = "conn " + (on ? "conn--on" : "conn--off");
  els.connText.textContent = text;
}

// ---------- Vẽ hàng đợi ----------
function renderQueue() {
  els.queue.innerHTML = "";
  items.forEach((it, i) => {
    const li = document.createElement("li");
    li.className = "qitem " + it.status;
    li.innerHTML = `
      <span class="num">${i + 1}</span>
      <span class="txt">${escapeHtml(it.prompt)}</span>
      <span class="tag ${it.status}">${statusLabel(it.status)}</span>`;
    els.queue.appendChild(li);
  });
  const done = items.filter((i) => i.status === "done").length;
  const finished = items.filter((i) =>
    ["done", "error", "timeout"].includes(i.status)
  ).length;
  els.progress.textContent = items.length ? `${done}/${items.length} xong` : "—";
  if (els.pfill) {
    els.pfill.style.width = items.length
      ? Math.round((finished / items.length) * 100) + "%"
      : "0%";
  }
}
function statusLabel(s) {
  return {
    pending: "Chờ",
    generating: "Đang tạo",
    done: "Xong",
    error: "Lỗi",
    timeout: "Quá giờ",
  }[s] || s;
}
function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

// ---------- Tên file ----------
function safeName(s) {
  return s
    .replace(/[\\/:*?"<>|]/g, "")
    .replace(/\s+/g, "-")
    .slice(0, 50)
    .replace(/-+$/, "");
}
function buildFilename(serial, prompt) {
  const folder = safeName(els.folder.value || "h2dev_flow") || "h2dev_flow";
  const snippet = safeName(prompt) || "image";
  const num = els.serial.checked ? String(serial).padStart(3, "0") + "_" : "";
  return `${folder}/${num}${snippet}.png`;
}

// ---------- Tải ảnh ----------
async function downloadImage(src, serial, prompt, tabId) {
  let url = src;
  // blob: thì nhờ content script đổi sang dataURL
  if (!/^https?:/i.test(src)) {
    const r = await sendToTab(tabId, { type: "TODATAURL", src });
    if (r && r.dataUrl) url = r.dataUrl;
    else throw new Error("Không tải được ảnh blob");
  }
  await chrome.downloads.download({
    url,
    filename: buildFilename(serial, prompt),
    conflictAction: "uniquify",
    saveAs: false,
  });
}

function bridgeEndpoint(path = "") {
  const url = new URL(els.bridgeUrl.value.trim() || "http://127.0.0.1:8765");
  if (!["127.0.0.1", "localhost"].includes(url.hostname) || url.protocol !== "http:") {
    throw new Error("Bridge chỉ được phép dùng http://127.0.0.1 hoặc localhost.");
  }
  return url.origin + path;
}

function bridgeHeaders() {
  const token = els.bridgeToken.value;
  if (token.length < 16) throw new Error("Bridge token phải có ít nhất 16 ký tự.");
  return { "X-VideoGenSystem-Token": token, "Content-Type": "application/json" };
}

function setBridgeStatus(text) {
  els.bridgeStatus.textContent = text;
}

function waitForDownload(downloadId, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => finish(new Error("Chrome download quá thời gian.")), timeoutMs);
    function finish(error) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      chrome.downloads.onChanged.removeListener(listener);
      if (error) reject(error);
      else resolve();
    }
    function listener(delta) {
      if (delta.id !== downloadId) return;
      if (delta.error) finish(new Error(delta.error.current || "Chrome download lỗi."));
      else if (delta.state?.current === "complete") finish();
    }
    chrome.downloads.onChanged.addListener(listener);
    chrome.downloads.search({ id: downloadId }, (downloads) => {
      const item = downloads?.[0];
      if (item?.error) finish(new Error(item.error));
      else if (item?.state === "complete") finish();
    });
  });
}

async function downloadBridgeImage(src, relativePath, tabId) {
  let url = src;
  if (!/^https?:/i.test(src)) {
    const converted = await sendToTab(tabId, { type: "TODATAURL", src });
    if (!converted?.dataUrl) throw new Error(converted?.error || "Không đổi được blob image.");
    url = converted.dataUrl;
  }
  const downloadId = await chrome.downloads.download({
    url,
    filename: relativePath,
    conflictAction: "overwrite",
    saveAs: false,
  });
  await waitForDownload(downloadId);
}

async function postBridgeResult(taskId, result) {
  const response = await fetch(bridgeEndpoint(`/v1/tasks/${taskId}/result`), {
    method: "POST",
    headers: bridgeHeaders(),
    body: JSON.stringify(result),
  });
  if (!response.ok) throw new Error(`Bridge từ chối kết quả: HTTP ${response.status}`);
}

async function runBridgeTask(task) {
  const tab = await checkConnection();
  if (!tab) throw new Error("Không có tab Google Flow đang mở.");
  if (!task || !/^[a-f0-9]{32}$/.test(task.id || "")) throw new Error("Bridge task ID không hợp lệ.");
  if (!/^video_gensystem_bridge\/[a-f0-9]{32}\.png$/.test(task.download_path || "")) {
    throw new Error("Bridge download path không hợp lệ.");
  }
  const uploaded = await sendToTab(tab.id, {
    type: "UPLOAD_REFERENCES",
    references: task.references || [],
  });
  if (!uploaded?.ok) throw new Error(uploaded?.error || "Không upload được reference.");
  const box = await sendToTab(tab.id, { type: "GET_BOX" });
  if (!box?.ok) throw new Error(box?.error || "Không tìm thấy prompt box.");
  const typed = await sendToBg({
    type: "DEBUG_SUBMIT",
    tabId: tab.id,
    x: box.x,
    y: box.y,
    prompt: task.prompt,
  });
  if (!typed?.ok) throw new Error(typed?.error || "Debugger không gửi được prompt.");
  const generated = await sendToTab(tab.id, { type: "WAIT_IMAGE" });
  if (generated?.timeout) {
    await postBridgeResult(task.id, { ok: false, timeout: true, error: "Google Flow quá thời gian sinh ảnh." });
    return;
  }
  if (!generated?.ok || !generated.src) throw new Error("Google Flow không trả ảnh mới.");
  await downloadBridgeImage(generated.src, task.download_path, tab.id);
  await postBridgeResult(task.id, { ok: true, download_path: task.download_path });
  await sendToBg({ type: "DEBUG_DETACH" });
}

async function pollBridge() {
  if (!els.bridgeEnabled.checked || bridgeBusy || running) return;
  try {
    const response = await fetch(bridgeEndpoint("/v1/tasks/next"), {
      headers: bridgeHeaders(),
      cache: "no-store",
    });
    if (response.status === 204) {
      setBridgeStatus("Đã kết nối · đang chờ job");
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const task = await response.json();
    bridgeBusy = true;
    setBridgeStatus(`Đang chạy task ${task.id.slice(0, 8)}…`);
    try {
      await runBridgeTask(task);
      setBridgeStatus("Hoàn thành task · đang chờ job");
    } catch (error) {
      try {
        await postBridgeResult(task.id, { ok: false, error: String(error.message || error) });
      } catch (_) {}
      setBridgeStatus(`Lỗi: ${String(error.message || error)}`);
      await sendToBg({ type: "DEBUG_DETACH" });
    } finally {
      bridgeBusy = false;
    }
  } catch (error) {
    setBridgeStatus(`Đang chờ worker local… (${String(error.message || error)})`);
  }
}

// ---------- Delay ngẫu nhiên ----------
function randDelay() {
  const a = Math.max(0, parseInt(els.delayMin.value) || 0);
  const b = Math.max(a, parseInt(els.delayMax.value) || 0);
  return (a + Math.random() * (b - a)) * 1000;
}

// ---------- Vòng lặp chính ----------
async function run() {
  const tab = await checkConnection();
  if (!tab) return;

  const list = parsePrompts();
  if (list.length === 0) {
    setConn(false, "Chưa có prompt nào");
    return;
  }

  items = list.map((p) => ({ prompt: p, status: "pending" }));
  renderQueue();

  running = true;
  els.start.disabled = true;
  els.stop.disabled = false;

  for (let i = 0; i < items.length; i++) {
    if (!running) break;

    items[i].status = "generating";
    renderQueue();

    // 1) lấy toạ độ ô prompt từ content script (+ chụp baseline ảnh)
    const box = await sendToTab(tab.id, { type: "GET_BOX" });
    if (!running) { items[i].status = "pending"; break; }
    if (!box || !box.ok) {
      items[i].status = "error";
      if (box && box.error) setConn(false, box.error);
      renderQueue();
      continue;
    }

    // 2) GÕ CHỮ THẬT + Enter qua background (chrome.debugger)
    const typed = await sendToBg({
      type: "DEBUG_SUBMIT",
      tabId: tab.id,
      x: box.x,
      y: box.y,
      prompt: items[i].prompt,
    });
    if (!running) { items[i].status = "pending"; break; }
    if (!typed || !typed.ok) {
      items[i].status = "error";
      setConn(
        false,
        typed && typed.error
          ? "Lỗi debugger: " + typed.error + " (đóng DevTools F12 trên tab Flow rồi thử lại)"
          : "Không gõ được (hãy đóng DevTools F12 trên tab Flow)"
      );
      renderQueue();
      // không tiếp tục nếu debugger lỗi
      break;
    }

    // 3) chờ ảnh mới rồi tải
    const resp = await sendToTab(tab.id, { type: "WAIT_IMAGE" });
    if (!running) { items[i].status = "pending"; break; }

    if (resp && resp.ok && resp.src) {
      try {
        await downloadImage(resp.src, i + 1, items[i].prompt, tab.id);
        items[i].status = "done";
      } catch (e) {
        console.warn("Download lỗi:", e);
        items[i].status = "error";
      }
    } else if (resp && resp.timeout) {
      items[i].status = "timeout";
    } else {
      items[i].status = "error";
    }
    renderQueue();

    // nghỉ ngẫu nhiên trước prompt kế (trừ prompt cuối)
    if (i < items.length - 1 && running) {
      await sleep(randDelay());
    }
  }

  // xong hàng đợi -> tách debugger để thanh vàng biến mất
  await sendToBg({ type: "DEBUG_DETACH" });

  running = false;
  els.start.disabled = false;
  els.stop.disabled = true;
}

async function stop() {
  running = false;
  els.stop.disabled = true;
  const tab = await getFlowTab();
  if (tab) await sendToTab(tab.id, { type: "STOP" });
  await sendToBg({ type: "DEBUG_DETACH" });
}

// ---------- Sự kiện ----------
els.prompts.addEventListener("input", () => {
  refreshCount();
  saveSettings();
});
[els.folder, els.serial, els.delayMin, els.delayMax].forEach((el) =>
  el.addEventListener("change", saveSettings)
);
[els.bridgeEnabled, els.bridgeUrl, els.bridgeToken].forEach((el) =>
  el.addEventListener("change", saveSettings)
);
els.loadTxt.addEventListener("click", () => els.txtFile.click());
els.txtFile.addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    els.prompts.value = reader.result;
    refreshCount();
    saveSettings();
  };
  reader.readAsText(f);
});
els.start.addEventListener("click", run);
els.stop.addEventListener("click", stop);

// ---------- Khởi động ----------
loadSettings();
checkConnection();
setInterval(checkConnection, 5000); // tự kiểm tra kết nối mỗi 5s
setInterval(pollBridge, 1500);

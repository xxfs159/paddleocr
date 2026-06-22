const state = {
  mode: "ocr",
  file: null,
  jobId: null,
  pollTimer: null,
  result: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const modeNames = {
  ocr: "PP-OCRv6 Medium",
  structure: "PP-StructureV3",
  vl: "PaddleOCR-VL 1.6",
};

const elements = {
  modeGrid: $("#modeGrid"),
  dropZone: $("#dropZone"),
  fileInput: $("#fileInput"),
  uploadIdle: $("#uploadIdle"),
  filePreview: $("#filePreview"),
  previewImage: $("#previewImage"),
  fileName: $("#fileName"),
  fileInfo: $("#fileInfo"),
  submit: $("#submitButton"),
  error: $("#errorMessage"),
  processing: $("#processingCard"),
  phase: $("#phaseText"),
  progressText: $("#progressText"),
  progressBar: $("#progressBar"),
  queueText: $("#queueText"),
  results: $("#results"),
};

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function showError(message) {
  elements.error.textContent = message;
  elements.error.classList.remove("hidden");
}

function clearError() {
  elements.error.classList.add("hidden");
  elements.error.textContent = "";
}

function selectMode(mode) {
  state.mode = mode;
  $$(".mode-card").forEach((card) => card.classList.toggle("active", card.dataset.mode === mode));
  $("#limitNote").textContent = mode === "vl"
    ? "图片 / PDF · 最大 15MB · PDF 最多 3 页"
    : "图片 / PDF · 最大 15MB · PDF 最多 10 页";
}

function setFile(file) {
  clearError();
  if (!file) return resetFile();
  if (file.size > 15 * 1024 * 1024) {
    showError("文件超过 15MB 限制");
    return;
  }
  state.file = file;
  elements.uploadIdle.classList.add("hidden");
  elements.filePreview.classList.remove("hidden");
  elements.fileName.textContent = file.name;
  elements.fileInfo.textContent = `${formatBytes(file.size)} · ${file.type || "未知类型"}`;
  elements.submit.disabled = false;
  const isPdf = file.name.toLowerCase().endsWith(".pdf");
  elements.filePreview.classList.toggle("pdf", isPdf);
  if (!isPdf) {
    elements.previewImage.src = URL.createObjectURL(file);
  } else {
    elements.previewImage.removeAttribute("src");
  }
}

function resetFile() {
  state.file = null;
  elements.fileInput.value = "";
  elements.uploadIdle.classList.remove("hidden");
  elements.filePreview.classList.add("hidden");
  elements.submit.disabled = true;
  elements.previewImage.removeAttribute("src");
}

async function loadSample(sampleId) {
  clearError();
  try {
    const response = await fetch(`/api/samples/${sampleId}`);
    if (!response.ok) throw new Error("示例文件读取失败");
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const filename = match ? decodeURIComponent(match[1]) : `${sampleId}.png`;
    selectMode(sampleId);
    setFile(new File([blob], filename, { type: blob.type }));
    elements.dropZone.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    showError(error.message);
  }
}

async function submitJob() {
  if (!state.file) return;
  clearError();
  elements.submit.disabled = true;
  elements.results.classList.add("hidden");
  elements.processing.classList.remove("hidden");
  updateProgress({ phase: "正在上传文件", progress: 2, queue_position: null });

  const form = new FormData();
  form.append("mode", state.mode);
  form.append("file", state.file);
  try {
    const response = await fetch("/api/jobs", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "任务提交失败");
    state.jobId = payload.id;
    updateProgress(payload);
    pollJob();
  } catch (error) {
    elements.processing.classList.add("hidden");
    elements.submit.disabled = false;
    showError(error.message);
  }
}

function updateProgress(job) {
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  elements.phase.textContent = job.phase || "等待处理";
  elements.progressText.textContent = `${progress}%`;
  elements.progressBar.style.width = `${progress}%`;
  if (job.queue_position) {
    elements.queueText.textContent = `前方还有 ${job.queue_position - 1} 个任务，请保持页面打开`;
  } else if (job.status === "loading_model") {
    elements.queueText.textContent = "首次加载会下载或初始化模型，可能需要几分钟";
  } else {
    elements.queueText.textContent = "GPU 单任务运行，处理期间文件始终保留在本机";
  }
}

async function pollJob() {
  clearTimeout(state.pollTimer);
  if (!state.jobId) return;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "任务状态读取失败");
    updateProgress(job);
    if (job.status === "completed") {
      elements.processing.classList.add("hidden");
      state.result = job.result;
      renderResult(job.result);
      return;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "模型处理失败");
    }
    state.pollTimer = setTimeout(pollJob, 1200);
  } catch (error) {
    elements.processing.classList.add("hidden");
    elements.submit.disabled = false;
    showError(error.message);
  }
}

function renderResult(result) {
  elements.results.classList.remove("hidden");
  $("#metricTime").textContent = `${result.elapsed_seconds.toFixed(2)}s`;
  $("#metricPages").textContent = result.page_count;
  $("#metricItems").textContent = result.item_count;
  $("#metricItemLabel").textContent = result.mode === "ocr" ? "识别文本" : "解析区块";
  $("#metricModel").textContent = modeNames[result.mode];
  renderVisuals(result);
  renderContent(result);
  renderMarkdown(result);
  renderDownloads(result);
  loadRawJson(result);
  activateTab("visual");
  elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderVisuals(result) {
  const grid = $("#visualGrid");
  grid.replaceChildren();
  const entries = Object.entries(result.artifact_urls)
    .filter(([name]) => name.startsWith("visuals/") && /\.(png|jpe?g|webp)$/i.test(name));
  $("#visualEmpty").classList.toggle("hidden", entries.length > 0);
  for (const [name, url] of entries) {
    const item = document.createElement("div");
    item.className = "visual-item";
    const image = document.createElement("img");
    image.src = url;
    image.alt = name;
    image.loading = "lazy";
    const caption = document.createElement("span");
    caption.textContent = name;
    item.append(image, caption);
    grid.append(item);
  }
}

function renderContent(result) {
  const list = $("#contentList");
  list.replaceChildren();
  result.pages.forEach((page) => {
    const divider = document.createElement("div");
    divider.className = "page-divider";
    divider.textContent = `PAGE ${String(page.page).padStart(2, "0")}`;
    list.append(divider);
    const items = result.mode === "ocr" ? page.lines : page.blocks;
    items.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "content-row";
      const number = document.createElement("span");
      number.className = "index";
      number.textContent = String(index + 1).padStart(2, "0");
      const text = document.createElement("span");
      text.className = "text";
      text.textContent = result.mode === "ocr" ? item.text : (item.content || "（无文本内容）");
      const meta = document.createElement("span");
      if (result.mode === "ocr") {
        meta.className = "score";
        meta.textContent = item.score == null ? "—" : `${(item.score * 100).toFixed(1)}%`;
      } else {
        meta.className = "label";
        meta.textContent = item.label;
      }
      row.append(number, text, meta);
      list.append(row);
    });
  });
  if (!list.children.length) {
    list.textContent = "没有可展示的识别内容。";
  }
}

function renderMarkdown(result) {
  const panel = $("#markdownPanel");
  if (result.markdown_html) {
    panel.innerHTML = result.markdown_html;
  } else {
    panel.textContent = result.mode === "ocr"
      ? "通用 OCR 模式不生成 Markdown，请查看“识别内容”。"
      : "模型没有生成 Markdown。";
  }
}

function renderDownloads(result) {
  const grid = $("#downloadGrid");
  grid.replaceChildren();
  for (const [name, url] of Object.entries(result.artifact_urls)) {
    const link = document.createElement("a");
    link.className = "download-card";
    link.href = url;
    link.download = "";
    const badge = document.createElement("b");
    badge.textContent = name.split(".").pop().slice(0, 5);
    const label = document.createElement("span");
    label.textContent = name;
    link.append(badge, label);
    grid.append(link);
  }
}

async function loadRawJson(result) {
  const view = $("#jsonView");
  view.textContent = "正在加载 JSON…";
  const url = result.artifact_urls["result.json"];
  if (!url) {
    view.textContent = "没有 JSON 文件。";
    return;
  }
  try {
    const response = await fetch(url);
    const data = await response.json();
    view.textContent = JSON.stringify(data, null, 2);
  } catch {
    view.textContent = "JSON 加载失败。";
  }
}

function activateTab(tabName) {
  $$("#tabs button").forEach((button) => button.classList.toggle("active", button.dataset.tab === tabName));
  $$(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === tabName));
}

async function cancelJob() {
  if (!state.jobId) return;
  clearTimeout(state.pollTimer);
  await fetch(`/api/jobs/${state.jobId}`, { method: "DELETE" }).catch(() => {});
  state.jobId = null;
  elements.processing.classList.add("hidden");
  elements.submit.disabled = !state.file;
}

function resetTask() {
  clearTimeout(state.pollTimer);
  state.jobId = null;
  state.result = null;
  resetFile();
  clearError();
  elements.results.classList.add("hidden");
  window.scrollTo({ top: $(".workspace").offsetTop - 30, behavior: "smooth" });
}

async function copyResult() {
  if (!state.result) return;
  let text = state.result.markdown_text || "";
  if (!text) {
    text = state.result.pages.flatMap((page) => page.lines || page.blocks || [])
      .map((item) => item.text || item.content || "").join("\n");
  }
  await navigator.clipboard.writeText(text);
  const button = $("#copyButton");
  const previous = button.textContent;
  button.textContent = "已复制";
  setTimeout(() => { button.textContent = previous; }, 1300);
}

async function updateHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();
    const pill = $("#systemPill");
    pill.classList.toggle("busy", Boolean(health.active_job_id));
    pill.classList.toggle("online", !health.active_job_id);
    if (health.gpu?.available) {
      const memory = `${health.gpu.memory_used_mb}/${health.gpu.memory_total_mb}MB`;
      $("#systemText").textContent = health.active_job_id
        ? `${modeNames[health.current_model] || "GPU"} 处理中 · ${memory}`
        : `${health.gpu.name} · ${memory}`;
    } else {
      $("#systemText").textContent = "服务在线 · GPU 状态未知";
    }
  } catch {
    $("#systemPill").classList.remove("online", "busy");
    $("#systemText").textContent = "本地引擎未连接";
  }
}

elements.modeGrid.addEventListener("click", (event) => {
  const card = event.target.closest(".mode-card");
  if (card) selectMode(card.dataset.mode);
});
elements.fileInput.addEventListener("change", () => setFile(elements.fileInput.files[0]));
$("#chooseButton").addEventListener("click", (event) => {
  event.stopPropagation();
  elements.fileInput.click();
});
$("#removeFile").addEventListener("click", (event) => {
  event.stopPropagation();
  resetFile();
});
["dragenter", "dragover"].forEach((name) => elements.dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  elements.dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => elements.dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
}));
elements.dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
$$(".sample-button").forEach((button) => button.addEventListener("click", () => loadSample(button.dataset.sample)));
elements.submit.addEventListener("click", submitJob);
$("#cancelButton").addEventListener("click", cancelJob);
$("#newTaskButton").addEventListener("click", resetTask);
$("#copyButton").addEventListener("click", copyResult);
$("#tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (button) activateTab(button.dataset.tab);
});

selectMode("ocr");
updateHealth();
setInterval(updateHealth, 5000);


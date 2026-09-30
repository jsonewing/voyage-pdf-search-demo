const STAGES = [
  { key: "upload", label: "Upload PDF" },
  { key: "extract", label: "Extract and chunk" },
  { key: "embed_lite", label: "Voyage 4 Lite" },
  { key: "embed_context", label: "Voyage Context 4" },
  { key: "embed_multimodal", label: "Voyage Multimodal 3.5" },
  { key: "store", label: "Store in Atlas" },
  { key: "indexes", label: "Build Search indexes" },
  { key: "sync", label: "Verify retrieval" },
];

const state = {
  config: null,
  setup: null,
  documents: [],
  enablementModules: [],
  activeEnablementKey: "",
  selectedSource: "",
  currentJob: null,
  pollTimer: null,
};

const uploadForm = document.querySelector("#upload-form");
const fileInput = document.querySelector("#pdf-file");
const dropZone = document.querySelector("#drop-zone");
const uploadButton = document.querySelector("#upload-button");
const documentSelect = document.querySelector("#document-select");
const searchForm = document.querySelector("#search-form");
const searchButton = document.querySelector("#search-button");
const results = document.querySelector("#results");
const enablementDialog = document.querySelector("#enablement-dialog");
const enablementCode = document.querySelector("#enablement-code code");
const enablementPre = document.querySelector("#enablement-code");
const copyCodeButton = document.querySelector("#copy-code");
const setupDialog = document.querySelector("#setup-dialog");
const setupForm = document.querySelector("#setup-form");
const setupCloseButton = document.querySelector("#setup-close");
const setupSaveButton = document.querySelector("#setup-save");
const atlasUriInput = document.querySelector("#setup-atlas-uri");
const voyageKeyInput = document.querySelector("#setup-voyage-key");
const openaiKeyInput = document.querySelector("#setup-openai-key");
const openaiBaseUrlInput = document.querySelector("#setup-openai-base-url");
const openaiApiModeInput = document.querySelector("#setup-openai-api-mode");
const openaiModelInput = document.querySelector("#setup-openai-model");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderEnablementModule(key) {
  const module = state.enablementModules.find((item) => item.key === key);
  if (!module) return;
  state.activeEnablementKey = key;
  document.querySelectorAll("#enablement-tabs button").forEach((button) => {
    const active = button.dataset.moduleKey === key;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelector("#enablement-file").textContent = module.path;
  document.querySelector("#enablement-description").textContent = module.description;
  enablementCode.textContent = module.code;
  enablementPre.scrollTo({ top: 0, left: 0 });
  renderEnablementNotes(module);
  copyCodeButton.disabled = false;
}

function jumpToEnablementAnchor(module, anchor) {
  const offset = module.code.indexOf(anchor);
  if (offset < 0) return;
  const line = module.code.slice(0, offset).split("\n").length;
  const lineHeight = Number.parseFloat(getComputedStyle(enablementCode).lineHeight) || 18;
  enablementPre.scrollTo({ top: Math.max(0, (line - 3) * lineHeight), behavior: "smooth" });
}

function renderEnablementNotes(module) {
  const container = document.querySelector("#enablement-notes");
  container.replaceChildren();
  const heading = document.createElement("div");
  heading.className = "notes-heading";
  heading.innerHTML = "<strong>Relevant code</strong><span>Select a note to jump to its implementation</span>";
  const grid = document.createElement("div");
  grid.className = "notes-grid";
  (module.notes || []).forEach((note) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "enablement-note";
    button.innerHTML = `<code>${escapeHtml(note.title)}</code><span>${escapeHtml(note.detail)}</span>`;
    button.setAttribute("aria-label", `${note.title}: ${note.detail}`);
    button.addEventListener("click", () => jumpToEnablementAnchor(module, note.anchor));
    grid.append(button);
  });
  container.append(heading, grid);
}

function renderEnablementTabs() {
  const tabs = document.querySelector("#enablement-tabs");
  tabs.replaceChildren();
  state.enablementModules.forEach((module, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.moduleKey = module.key;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");
    button.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(module.label)}</strong>`;
    button.addEventListener("click", () => renderEnablementModule(module.key));
    tabs.append(button);
  });
  renderEnablementModule(state.enablementModules[0]?.key);
}

async function openEnablement() {
  enablementDialog.showModal();
  document.body.classList.add("dialog-open");
  if (state.enablementModules.length) return;
  try {
    const payload = await api("/api/enablement");
    state.enablementModules = payload.modules || [];
    renderEnablementTabs();
  } catch (error) {
    document.querySelector("#enablement-file").textContent = "Source unavailable";
    document.querySelector("#enablement-description").textContent = error.message;
    enablementCode.textContent = "The implementation reference could not be loaded.";
  }
}

function closeEnablement() {
  enablementDialog.close();
  document.body.classList.remove("dialog-open");
}

function renderConnectionState() {
  const button = document.querySelector("#setup-open");
  const label = document.querySelector("#setup-open-label");
  const configured = Boolean(state.setup?.configured);
  button.classList.toggle("connected", configured);
  button.classList.toggle("required", !configured);
  label.textContent = configured ? "Connected" : "Set up connection";
  button.title = configured
    ? `Connected to MongoDB Atlas.${state.setup.openai_configured ? ` RAG: ${state.setup.openai_rag_model} via ${String(state.setup.openai_api_mode).replaceAll("_", " ")}.` : ""} Select to change local settings.`
    : "Atlas URI and Voyage API key are required";
  fileInput.disabled = !configured;
  uploadButton.disabled = !configured;
  document.querySelectorAll('input[name="models"]').forEach((input) => {
    input.disabled = !configured;
  });
  const rag = document.querySelector("#rag");
  const ragAvailable = Boolean(state.setup?.openai_configured);
  if (!ragAvailable) rag.checked = false;
  rag.disabled = !configured || !ragAvailable;
  rag.closest(".rag-control").title = ragAvailable
    ? "Generate a grounded executive summary from each pipeline's retrieved evidence"
    : "Add an optional OpenAI API key in Connection settings to enable RAG answers";
}

function openSetup(required = false) {
  setupDialog.dataset.required = String(required);
  setupCloseButton.disabled = required;
  atlasUriInput.value = "";
  voyageKeyInput.value = "";
  openaiKeyInput.value = "";
  atlasUriInput.placeholder = state.setup?.atlas_configured
    ? "Saved locally; leave blank to keep the current URI"
    : "mongodb+srv://username:password@cluster.mongodb.net/";
  voyageKeyInput.placeholder = state.setup?.voyage_configured
    ? "Saved locally; leave blank to keep the current key"
    : "pa-...";
  openaiKeyInput.placeholder = state.setup?.openai_configured
    ? "Saved locally; leave blank to keep the current key"
    : "sk-... or enterprise gateway key (optional)";
  openaiBaseUrlInput.value = state.setup?.openai_base_url || "https://api.openai.com/v1";
  openaiApiModeInput.value = state.setup?.openai_api_mode || "responses";
  openaiModelInput.value = state.setup?.openai_rag_model || "gpt-5-mini";
  document.querySelector("#setup-database").value =
    state.setup?.database || "voyage_pdf_live_demo";
  document.querySelector("#setup-collection").value =
    state.setup?.collection || "pdf_chunks";
  document.querySelector("#setup-show-values").checked = false;
  atlasUriInput.type = "password";
  voyageKeyInput.type = "password";
  openaiKeyInput.type = "password";
  openaiBaseUrlInput.type = "password";
  document.querySelector("#setup-feedback").className = "setup-feedback";
  document.querySelector("#setup-feedback").textContent = required
    ? "Complete this one-time setup to enable uploads and search."
    : "Leave a saved credential blank to keep its current value.";
  document.querySelector("#setup-storage").textContent =
    state.setup?.storage ? `Saved to ${state.setup.storage}` : "Saved locally in this application folder";
  if (!setupDialog.open) setupDialog.showModal();
  document.body.classList.add("dialog-open");
}

function closeSetup() {
  if (setupDialog.dataset.required === "true") return;
  setupDialog.close();
  document.body.classList.remove("dialog-open");
}

async function refreshConfiguredApp() {
  state.config = await api("/api/config");
  renderModelOptions();
  const weights = state.config.hybrid_weights;
  document.querySelector("#hybrid-copy").textContent =
    `${Math.round(weights.vector * 100)}% semantic and ${Math.round(weights.lexical * 100)}% lexical weighted rank fusion.`;
  document.querySelector(".format-badge").textContent = `PDF · ${state.config.upload_max_mb} MB max`;
  await loadDocuments();
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  return body;
}

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function renderEmptyStages() {
  renderStages(STAGES.map((stage) => ({ ...stage, status: "pending", detail: "" })));
}

function renderStages(stages) {
  const container = document.querySelector("#stage-list");
  const template = document.querySelector("#stage-template");
  container.replaceChildren();
  stages.forEach((stage) => {
    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector(".stage-row");
    row.classList.add(stage.status || "pending");
    fragment.querySelector(".stage-copy strong").textContent = stage.label;
    fragment.querySelector(".stage-copy small").textContent = stage.detail || "Waiting";
    fragment.querySelector(".stage-status").textContent = stage.status || "pending";
    container.appendChild(fragment);
  });
}

function renderJob(job) {
  state.currentJob = job;
  document.querySelector("#progress-bar").style.width = `${job.progress || 0}%`;
  const badge = document.querySelector("#job-state");
  badge.className = `state-badge ${job.status}`;
  badge.textContent = job.status === "processing" ? `${job.progress}%` : job.status;
  document.querySelector("#job-message").textContent = job.message;
  renderStages(job.steps);

  const processing = job.status === "processing";
  uploadButton.disabled = processing;
  document.querySelectorAll('input[name="models"]').forEach((input) => {
    input.disabled = processing;
  });
  uploadButton.textContent = processing ? "Building pipelines..." : "Build search pipelines";
  if (job.status === "ready") {
    state.selectedSource = job.source_id;
    searchButton.disabled = false;
  }
}

async function pollJob(jobId) {
  clearTimeout(state.pollTimer);
  try {
    const job = await api(`/api/jobs/${jobId}`);
    renderJob(job);
    if (job.status === "processing") {
      state.pollTimer = setTimeout(() => pollJob(jobId), 1200);
      return;
    }
    if (job.status === "ready") {
      await loadDocuments(job.source_id);
    }
  } catch (error) {
    showError(error.message);
    uploadButton.disabled = false;
  }
}

function setSelectedFile(file) {
  if (!file) {
    document.querySelector("#file-name").textContent = "Select a PDF";
    document.querySelector("#file-detail").textContent = "Text PDFs with tables are supported";
    return;
  }
  document.querySelector("#file-name").textContent = file.name;
  document.querySelector("#file-detail").textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
}

function renderDocuments(preferredSource = "") {
  documentSelect.replaceChildren();
  if (!state.documents.length) {
    const option = new Option("No indexed PDFs found", "");
    documentSelect.append(option);
    state.selectedSource = "";
    searchButton.disabled = true;
    document.querySelector("#source-models").textContent = "No model lanes available";
    return;
  }
  state.documents.forEach((document) => {
    const modelCount = document.available_model_keys?.length || 0;
    const suffix = `${document.pages || "?"} pages · ${document.chunks} chunks · ${modelCount} model${modelCount === 1 ? "" : "s"}`;
    const option = new Option(`${document.filename} — ${suffix}`, document.source_id);
    documentSelect.append(option);
  });
  const desired = preferredSource || state.selectedSource || state.documents[0].source_id;
  documentSelect.value = state.documents.some((item) => item.source_id === desired)
    ? desired
    : state.documents[0].source_id;
  state.selectedSource = documentSelect.value;
  searchButton.disabled = false;
  renderSourceModels();
}

function renderSourceModels() {
  const selected = state.documents.find((item) => item.source_id === state.selectedSource);
  const labels = (selected?.available_model_keys || []).map((key) =>
    state.config?.models.find((model) => model.key === key)?.label || key
  );
  document.querySelector("#source-models").textContent = labels.length
    ? `Available: ${labels.join(" · ")}`
    : "Legacy document: available vector lanes are detected at query time";
}

function renderModelOptions() {
  const container = document.querySelector("#model-options");
  container.innerHTML = state.config.models.map((model) => `
    <label class="model-option">
      <input type="checkbox" name="models" value="${escapeHtml(model.key)}" checked ${state.setup?.configured ? "" : "disabled"} />
      <span>
        <strong>${escapeHtml(model.label)}</strong>
        <small>${escapeHtml(model.representation)}</small>
      </span>
    </label>
  `).join("");
}

async function loadDocuments(preferredSource = "") {
  const payload = await api("/api/documents");
  state.documents = payload.documents;
  renderDocuments(preferredSource);
}

function updateModeSummary() {
  const mode = currentMode();
  const rerank = document.querySelector("#rerank");
  const lexicalOnly = mode === "lexical";
  if (lexicalOnly) rerank.checked = false;
  rerank.disabled = lexicalOnly;
  rerank.closest(".rerank-control").title = lexicalOnly
    ? "Reranking is available for Vector and Hybrid searches"
    : "Retrieve 20 candidates and use Voyage Rerank to select the final 5";
  document.querySelectorAll("[data-mode-summary]").forEach((item) => {
    item.classList.toggle("active", item.dataset.modeSummary === mode);
  });
}

function scoreLabel(result) {
  const retrieval = typeof result.score_value === "number"
    ? result.score_value.toFixed(4)
    : "ranked";
  if (typeof result.rerank_score === "number") {
    return `R ${result.rerank_score.toFixed(4)}<small>base ${retrieval}</small>`;
  }
  return retrieval;
}

function pipelineCard(pipeline) {
  const evidence = pipeline.results.length
    ? pipeline.results.map((result, index) => {
      const visual = pipeline.key === "voyage_multimodal_3_5" && result.visual?.kind
        ? ` · visual: ${String(result.visual.kind).replaceAll("_", " ")}`
        : "";
      return `
      <div class="evidence-row">
        <span class="rank">${index + 1}</span>
        <span class="evidence-meta">Page ${escapeHtml(result.page)} · ${escapeHtml(String(result.chunk_kind || "chunk").replace("_", " "))}${escapeHtml(visual)} · ${escapeHtml(result.section_title || "Untitled section")}</span>
        <span class="evidence-score">${scoreLabel(result)}</span>
        <span class="evidence-text">${escapeHtml(result.text)}</span>
      </div>`;
    }).join("")
    : '<div class="results-empty">No matching evidence returned.</div>';

  let ragAnswer = "";
  if (pipeline.rag?.status === "complete") {
    const generated = escapeHtml(pipeline.rag.answer || "No generated answer returned.")
      .replaceAll("\n", "<br>");
    ragAnswer = `
      <div class="rag-answer">
        <div class="rag-answer-head">
          <span>OpenAI grounded executive summary</span>
          <small>${escapeHtml(pipeline.rag.model)} · ${escapeHtml(String(pipeline.rag.api_mode || "responses").replaceAll("_", " "))} · ${Number(pipeline.rag.latency_ms).toFixed(0)} ms generation</small>
        </div>
        <p>${generated}</p>
        ${pipeline.rag.evidence_count > 0 ? `<small class="citation-note">Citations [1]–[${pipeline.rag.evidence_count}] map to the evidence ranks below.</small>` : ""}
      </div>`;
  } else if (pipeline.rag?.status === "error") {
    ragAnswer = `
      <div class="rag-answer rag-error">
        <div class="rag-answer-head"><span>OpenAI generation unavailable</span></div>
        <p>${escapeHtml(pipeline.rag.error)}</p>
      </div>`;
  }

  return `
    <article class="pipeline-panel">
      <header class="pipeline-head">
        <div class="pipeline-title">
          <strong>${escapeHtml(pipeline.label)}${pipeline.reranked ? " + Rerank" : ""}</strong>
          <small>${escapeHtml(pipeline.model)} · ${escapeHtml(pipeline.representation)}${pipeline.reranked ? ` · ${escapeHtml(pipeline.rerank_model)}` : ""}</small>
        </div>
        <div class="latency"><strong>${Number(pipeline.latency_ms).toFixed(0)} ms</strong><span>${pipeline.reranked ? `${Number(pipeline.rerank_ms).toFixed(0)} ms rerank` : "retrieval"}</span></div>
      </header>
      ${ragAnswer}
      <div class="answer-block">
        <span>${pipeline.reranked ? "Reranked" : "Retrieval-only"} extractive summary</span>
        <p>${escapeHtml(pipeline.answer || "No answer-bearing passage was returned.")}</p>
      </div>
      <div class="evidence-list">${evidence}</div>
    </article>`;
}

function renderSearch(payload) {
  const pipelines = payload.pipelines || [];
  let summary = `${payload.mode.toUpperCase()} · ${pipelines.length} pipeline${pipelines.length === 1 ? "" : "s"}`;
  if (payload.reranked) summary += ` · ${escapeHtml(state.config?.rerank_model || "Voyage rerank")}`;
  if (payload.rag) summary += ` · OpenAI RAG (${escapeHtml(state.config?.rag_model || "configured model")})`;
  if (pipelines.length > 1) {
    const first = new Set(pipelines[0].results.map((result) => result._id));
    const overlap = [...first].filter((id) =>
      pipelines.slice(1).every((pipeline) => pipeline.results.some((result) => result._id === id))
    ).length;
    const depth = Math.max(...pipelines.map((pipeline) => pipeline.results.length));
    summary += ` · Top-${depth} shared by all ${overlap}`;
  }
  document.querySelector("#comparison-summary").textContent = summary;
  results.className = "pipeline-grid" + (pipelines.length === 1 ? " single" : "");
  results.innerHTML = pipelines.map(pipelineCard).join("");
}

function showError(message) {
  results.className = "error-box";
  results.textContent = message;
  document.querySelector("#comparison-summary").textContent = "Request failed";
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;
  uploadButton.disabled = true;
  uploadButton.textContent = "Uploading...";
  const form = new FormData();
  form.append("file", file);
  const selectedModels = [...document.querySelectorAll('input[name="models"]:checked')];
  if (!selectedModels.length) {
    uploadButton.disabled = false;
    uploadButton.textContent = "Build search pipelines";
    showError("Select at least one Voyage model.");
    return;
  }
  selectedModels.forEach((input) => form.append("models", input.value));
  try {
    const job = await api("/api/upload", { method: "POST", body: form });
    renderJob(job);
    pollJob(job.id);
  } catch (error) {
    uploadButton.disabled = false;
    uploadButton.textContent = "Build search pipelines";
    showError(error.message);
  }
});

fileInput.addEventListener("change", () => setSelectedFile(fileInput.files[0]));

["dragenter", "dragover"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});

dropZone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  setSelectedFile(file);
});

documentSelect.addEventListener("change", () => {
  state.selectedSource = documentSelect.value;
  searchButton.disabled = !state.selectedSource;
  renderSourceModels();
});

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", updateModeSummary);
});

document.querySelector("#enablement-open").addEventListener("click", openEnablement);
document.querySelector("#enablement-close").addEventListener("click", closeEnablement);
enablementDialog.addEventListener("click", (event) => {
  if (event.target === enablementDialog) closeEnablement();
});
enablementDialog.addEventListener("close", () => document.body.classList.remove("dialog-open"));
copyCodeButton.addEventListener("click", async () => {
  const module = state.enablementModules.find((item) => item.key === state.activeEnablementKey);
  if (!module) return;
  await navigator.clipboard.writeText(module.code);
  copyCodeButton.textContent = "Copied";
  window.setTimeout(() => { copyCodeButton.textContent = "Copy code"; }, 1400);
});

document.querySelector("#setup-open").addEventListener("click", () => openSetup(false));
setupCloseButton.addEventListener("click", closeSetup);
setupDialog.addEventListener("cancel", (event) => {
  if (setupDialog.dataset.required === "true") event.preventDefault();
});
setupDialog.addEventListener("close", () => {
  if (setupDialog.dataset.required === "true") {
    window.setTimeout(() => {
      if (!setupDialog.open) setupDialog.showModal();
      document.body.classList.add("dialog-open");
    }, 0);
    return;
  }
  document.body.classList.remove("dialog-open");
});
document.querySelector("#setup-show-values").addEventListener("change", (event) => {
  const type = event.target.checked ? "text" : "password";
  atlasUriInput.type = type;
  voyageKeyInput.type = type;
  openaiKeyInput.type = type;
  openaiBaseUrlInput.type = type;
});
setupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const feedback = document.querySelector("#setup-feedback");
  setupSaveButton.disabled = true;
  setupSaveButton.textContent = "Verifying...";
  feedback.className = "setup-feedback checking";
  feedback.textContent = "Checking Atlas, Voyage, and the optional OpenAI connection.";
  try {
    state.setup = await api("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        atlas_uri: atlasUriInput.value,
        voyage_api_key: voyageKeyInput.value,
        openai_api_key: openaiKeyInput.value,
        database: document.querySelector("#setup-database").value,
        collection: document.querySelector("#setup-collection").value,
        openai_base_url: openaiBaseUrlInput.value,
        openai_api_mode: openaiApiModeInput.value,
        openai_rag_model: openaiModelInput.value,
      }),
    });
    renderConnectionState();
    feedback.className = "setup-feedback success";
    feedback.textContent = state.setup.message;
    await refreshConfiguredApp();
    setupDialog.dataset.required = "false";
    window.setTimeout(closeSetup, 450);
    document.querySelector("#job-message").textContent =
      "Connection ready. Upload a PDF to build search pipelines.";
  } catch (error) {
    feedback.className = "setup-feedback error";
    feedback.textContent = error.message;
  } finally {
    setupSaveButton.disabled = false;
    setupSaveButton.textContent = "Verify and save";
  }
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.querySelector("#question").value.trim();
  if (!query || !state.selectedSource) return;
  searchButton.disabled = true;
  const ragEnabled = document.querySelector("#rag").checked;
  searchButton.textContent = ragEnabled ? "Generating..." : "Searching...";
  results.className = "results-loading";
  results.textContent = ragEnabled
    ? "Retrieving evidence, then generating grounded executive summaries"
    : "Running Atlas retrieval pipelines";
  try {
    const payload = await api("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        source_id: state.selectedSource,
        mode: currentMode(),
        limit: 5,
        rerank: document.querySelector("#rerank").checked,
        rag: ragEnabled,
      }),
    });
    renderSearch(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    searchButton.disabled = false;
    searchButton.textContent = "Search";
  }
});

async function initialize() {
  renderEmptyStages();
  updateModeSummary();
  try {
    state.setup = await api("/api/setup");
    renderConnectionState();
    state.config = await api("/api/config");
    renderModelOptions();
    const weights = state.config.hybrid_weights;
    document.querySelector("#hybrid-copy").textContent =
      `${Math.round(weights.vector * 100)}% semantic and ${Math.round(weights.lexical * 100)}% lexical weighted rank fusion.`;
    document.querySelector(".format-badge").textContent = `PDF · ${state.config.upload_max_mb} MB max`;
    if (state.setup.configured) {
      await loadDocuments();
    } else {
      renderDocuments();
      document.querySelector("#job-message").textContent =
        "Connect MongoDB Atlas and Voyage AI to begin.";
      openSetup(true);
    }
  } catch (error) {
    document.querySelector("#job-message").textContent = error.message;
  }
}

initialize();

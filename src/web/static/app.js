const state = {
  view: "dashboard",
  facets: null,
  selectedThesisId: null,
  selectedConcept: null,
  currentDraft: null,
  importItems: [],
  selectedImportIndex: -1,
  importBusy: false,
  llmSuggestions: null,
  datasetColumns: [],
  datasetRows: [],
  ragBusy: false,
  searchPage: 1,
  searchPageSize: 20,
  searchTotal: 0,
  searchTotalPages: 0,
  ragPage: 1,
  ragPageSize: 20,
  ragTotalPages: 0,
  ragHasPrevious: false,
  ragHasNext: false,
  ragQuestion: "",
  ragAllResults: false,
};

const viewTitles = {
  dashboard: ["Dashboard", "Overview of the extracted thesis graph."],
  search: ["Thesis Search", "Search and filter thesis metadata through graph relations."],
  concepts: ["Concepts", "Explore frequent concepts and their connected theses."],
  dataset: ["Dataset CSV", "View every extracted thesis row in one table."],
  rag: ["Ask / RAG", "Ask questions over local thesis metadata and cited sources."],
  import: ["Import PDF", "Add a new thesis through extraction, review, and approval."],
};

const api = {
  async get(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
  },
  async postForm(path, formData) {
    const response = await fetch(path, {
      method: "POST",
      body: formData,
    });
    return parseResponse(response);
  },
  async postJson(path, data) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return parseResponse(response);
  },
  async delete(path) {
    const response = await fetch(path, { method: "DELETE" });
    return parseResponse(response);
  },
};

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(formatApiError(data.detail, `${response.status} ${response.statusText}`));
  }
  return data;
}

function formatApiError(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
        return [location, item.msg].filter(Boolean).join(": ");
      })
      .filter(Boolean)
      .join("; ") || fallback;
  }
  if (detail && typeof detail === "object") {
    return detail.msg || JSON.stringify(detail);
  }
  return fallback;
}

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return [...document.querySelectorAll(selector)];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

function truncate(value, length = 120) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length - 3)}...` : text;
}

async function init() {
  bindNavigation();
  bindControls();
  await refreshAll();
}

function bindNavigation() {
  qsa(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
}

function bindControls() {
  qs("#refresh-button").addEventListener("click", refreshAll);
  qs("#search-button").addEventListener("click", () => runSearch({ page: 1 }));
  qs("#clear-button").addEventListener("click", clearSearch);
  qs("#show-all-button").addEventListener("click", showAllSearchResults);
  qs("#previous-page-button").addEventListener("click", () => runSearch({ page: state.searchPage - 1 }));
  qs("#next-page-button").addEventListener("click", () => runSearch({ page: state.searchPage + 1 }));
  qs("#upload-form").addEventListener("submit", uploadImport);
  qs("#pdf-file").addEventListener("change", updateFileLabel);
  qs("#approve-import-button").addEventListener("click", approveCurrentImport);
  qs("#discard-import-button").addEventListener("click", discardCurrentImport);
  qs("#generate-llm-button").addEventListener("click", generateLlmSuggestions);
  qs("#apply-llm-button").addEventListener("click", applyLlmSuggestions);
  qs("#copy-csv-button").addEventListener("click", copyDatasetCsv);
  qs("#rag-ask-button").addEventListener("click", askRag);
  qs("#rag-show-all").addEventListener("change", syncRagControls);
  qs("#rag-previous-page-button").addEventListener("click", () => loadRagSourcesPage(state.ragPage - 1));
  qs("#rag-next-page-button").addEventListener("click", () => loadRagSourcesPage(state.ragPage + 1));
  qs("#profile-close-button").addEventListener("click", closeThesisProfile);
  qs("#profile-modal").addEventListener("click", (event) => {
    if (event.target.id === "profile-modal") closeThesisProfile();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeThesisProfile();
  });
  qs("#text-query").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runSearch({ page: 1 });
  });
  qs("#rag-question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) askRag();
  });
}

function setView(view) {
  state.view = view;
  qsa(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  qsa(".view").forEach((section) => section.classList.remove("active"));
  qs(`#${view}-view`).classList.add("active");
  qs("#view-title").textContent = viewTitles[view][0];
  qs("#view-subtitle").textContent = viewTitles[view][1];
  if (view === "dataset" && state.datasetRows.length === 0) {
    loadDataset();
  }
}

async function refreshAll() {
  await Promise.all([loadDashboard(), loadFacets(), loadDataset()]);
  await runSearch({ page: 1 });
  await loadConceptIndex();
}

async function loadDashboard() {
  const summary = await api.get("/api/summary");
  const nodeCounts = summary.node_counts || {};
  const edgeCounts = summary.edge_counts || {};
  const metrics = [
    ["Theses", nodeCounts.Thesis],
    ["Concepts", nodeCounts.Concept],
    ["Keywords", nodeCounts.Keyword],
    ["Relations", summary.edges_total],
  ];

  qs("#metric-grid").innerHTML = metrics
    .map(([label, value]) => `
      <article class="metric-card">
        <span>${escapeHtml(label)}</span>
        <strong>${formatNumber(value)}</strong>
      </article>
    `)
    .join("");

  renderRankList(qs("#top-concepts"), summary.top_concepts || []);
  renderRankList(qs("#top-use-cases"), summary.top_use_cases || []);
  renderRankList(qs("#top-methodologies"), summary.top_methodologies || []);

  if (edgeCounts.RELATED_TO && state.view === "dashboard") {
    qs("#view-subtitle").textContent = `${formatNumber(edgeCounts.RELATED_TO)} thesis similarity links are available.`;
  }
}

async function loadFacets() {
  state.facets = await api.get("/api/facets");
  fillSelect(qs("#concept-filter"), state.facets.concepts || [], "All concepts");
  fillSelect(qs("#year-filter"), state.facets.years || [], "All years");
  fillSelect(qs("#level-filter"), state.facets.master_levels || [], "All levels");
  fillSelect(qs("#track-filter"), state.facets.tracks || [], "All tracks");
}

function fillSelect(select, items, defaultLabel) {
  select.innerHTML = `<option value="">${escapeHtml(defaultLabel)}</option>${items
    .map((item) => `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)}</option>`)
    .join("")}`;
}

function renderRankList(container, items) {
  container.innerHTML = items
    .map((item) => `
      <div class="rank-item">
        <span class="rank-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
        <span class="rank-count">${formatNumber(item.incoming_edges)}</span>
      </div>
    `)
    .join("");
}

async function loadDataset() {
  const status = qs("#dataset-status");
  if (!status) return;
  status.textContent = "Loading complete dataset...";
  status.className = "status-banner working-banner";
  try {
    const payload = await api.get("/api/dataset");
    state.datasetColumns = payload.columns || [];
    state.datasetRows = payload.rows || [];
    renderDataset();
    status.textContent = "Complete CSV dataset loaded.";
    status.className = "status-banner success-banner";
  } catch (error) {
    status.textContent = `Dataset load failed: ${error.message}`;
    status.className = "status-banner error-banner";
  }
}

function renderDataset() {
  qs("#dataset-count").textContent = `${formatNumber(state.datasetRows.length)} rows | ${formatNumber(state.datasetColumns.length)} columns`;
  qs("#dataset-head").innerHTML = `
    <tr>
      ${state.datasetColumns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}
    </tr>
  `;
  qs("#dataset-body").innerHTML = state.datasetRows
    .map((row) => `
      <tr>
        ${state.datasetColumns
          .map((column) => `<td class="csv-cell">${escapeHtml(row[column] ?? "")}</td>`)
          .join("")}
      </tr>
    `)
    .join("");
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

async function copyDatasetCsv() {
  if (!state.datasetRows.length) {
    renderDatasetCopyStatus("Load the dataset before copying.", "warning");
    return;
  }
  const lines = [
    state.datasetColumns.map(csvEscape).join(","),
    ...state.datasetRows.map((row) => state.datasetColumns.map((column) => csvEscape(row[column])).join(",")),
  ];
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    renderDatasetCopyStatus("CSV copied to clipboard.", "success");
  } catch (_error) {
    renderDatasetCopyStatus("Copy failed in this browser. Use Download CSV instead.", "warning");
  }
}

function renderDatasetCopyStatus(message, kind) {
  const status = qs("#dataset-status");
  status.textContent = message;
  status.className = `status-banner ${kind || "muted"}-banner`;
}

async function askRag() {
  const question = valueOf("#rag-question");
  const topK = normalizedRagTopK();
  const useLlm = qs("#rag-use-llm").checked;
  const showAll = qs("#rag-show-all").checked;
  if (!question) {
    renderRagStatus("Enter a question first.", "warning");
    return;
  }
  if (question.length < 2) {
    renderRagStatus("Question must be at least 2 characters.", "warning");
    return;
  }
  state.ragQuestion = question;
  state.ragAllResults = showAll;
  state.ragPage = 1;
  setRagBusy(true);
  renderRagStatus(
    useLlm
      ? "Retrieving sources and asking local Ollama..."
      : showAll
        ? "Retrieving answer and the first source page..."
        : "Retrieving local thesis sources...",
    "working",
  );
  try {
    if (showAll) {
      const [answer, sources] = await Promise.all([
        api.postJson("/api/rag/answer", {
          question,
          top_k: Math.min(topK, 5),
          use_llm: useLlm,
        }),
        api.postJson("/api/rag/search", {
          question,
          all_results: true,
          page: 1,
          page_size: state.ragPageSize,
        }),
      ]);
      renderRagResult(answer, sources);
      renderRagStatus(
        `Retrieved ${formatNumber(sources.count || 0)} of ${formatNumber(sources.total || 0)} source theses.`,
        answer.answer_mode === "ollama_unavailable" ? "warning" : "success",
      );
    } else {
      const result = await api.postJson("/api/rag/answer", {
        question,
        top_k: topK,
        use_llm: useLlm,
      });
      renderRagResult(result);
      renderRagStatus(`Retrieved ${formatNumber(result.results?.length || 0)} source theses.`, result.answer_mode === "ollama_unavailable" ? "warning" : "success");
    }
  } catch (error) {
    renderRagStatus(error.message, "error");
  } finally {
    setRagBusy(false);
  }
}

function normalizedRagTopK() {
  const input = qs("#rag-top-k");
  const parsed = Number(input.value || 5);
  const integer = Number.isFinite(parsed) ? Math.trunc(parsed) : 5;
  const clamped = Math.min(20, Math.max(1, integer));
  input.value = String(clamped);
  return clamped;
}

async function loadRagSourcesPage(page) {
  if (!state.ragQuestion || !state.ragAllResults) return;
  const requestedPage = Math.max(1, Number.isFinite(Number(page)) ? Math.trunc(Number(page)) : 1);
  setRagBusy(true);
  renderRagStatus(`Loading source page ${formatNumber(requestedPage)}...`, "working");
  try {
    const result = await api.postJson("/api/rag/search", {
      question: state.ragQuestion,
      all_results: true,
      page: requestedPage,
      page_size: state.ragPageSize,
    });
    renderRagSources(result);
    renderRagStatus(`Showing ${formatNumber(result.count || 0)} of ${formatNumber(result.total || 0)} source theses.`, "success");
  } catch (error) {
    renderRagStatus(error.message, "error");
  } finally {
    setRagBusy(false);
  }
}

function renderRagResult(result, sourcePage = null) {
  qs("#rag-meta").textContent = `${result.embedding_model || "local"} | ${result.embedding_dimensions || 0} dimensions`;
  qs("#rag-answer-mode").textContent = result.answer_mode === "ollama" ? "Ollama" : "Local";
  qs("#rag-answer").classList.remove("empty-state");
  qs("#rag-answer").innerHTML = `
    <p>${escapeHtml(result.answer || "No answer generated.")}</p>
    ${result.llm_error ? `<p class="muted">${escapeHtml(result.llm_error)}</p>` : ""}
  `;
  renderRagSources(sourcePage || result);
}

function renderRagSources(result) {
  const rows = result.results || [];
  const total = result.total ?? rows.length;
  const offset = result.offset || 0;
  const first = total ? offset + 1 : 0;
  const last = total ? offset + rows.length : 0;
  qs("#rag-source-count").textContent = state.ragAllResults && total > rows.length
    ? `${formatNumber(first)}-${formatNumber(last)} of ${formatNumber(total)} sources`
    : `${formatNumber(rows.length)} sources`;
  qs("#rag-results").innerHTML = rows.map(renderRagSource).join("") || '<div class="empty-state">No sources found.</div>';
  qsa(".profile-button").forEach((button) => {
    button.addEventListener("click", () => openThesisProfile(button.dataset.thesisId));
  });
  renderRagPagination(result);
}

function renderRagPagination(result) {
  const pagination = qs("#rag-pagination");
  const totalPages = result.total_pages || 0;
  if (!state.ragAllResults || totalPages <= 1) {
    state.ragTotalPages = 0;
    state.ragHasPrevious = false;
    state.ragHasNext = false;
    pagination.classList.add("hidden");
    qs("#rag-pagination-status").textContent = "";
    qs("#rag-previous-page-button").disabled = true;
    qs("#rag-next-page-button").disabled = true;
    return;
  }
  state.ragPage = result.page || 1;
  state.ragTotalPages = totalPages;
  state.ragHasPrevious = Boolean(result.has_previous);
  state.ragHasNext = Boolean(result.has_next);
  pagination.classList.remove("hidden");
  qs("#rag-pagination-status").textContent = `Page ${formatNumber(state.ragPage)} of ${formatNumber(totalPages)} | ${formatNumber(result.page_size || state.ragPageSize)} per page`;
  qs("#rag-previous-page-button").disabled = !state.ragHasPrevious;
  qs("#rag-next-page-button").disabled = !state.ragHasNext;
}

function renderRagSource(row) {
  return `
    <article class="rag-source-card">
      <div class="rag-source-header">
        <strong>${escapeHtml(row.thesis_id)} | ${escapeHtml(row.year)} | ${escapeHtml(row.master_level)} | ${escapeHtml(row.track)}</strong>
        <span class="rag-score">${escapeHtml(Number(row.score || 0).toFixed(3))}</span>
      </div>
      <h4>${escapeHtml(row.title)}</h4>
      <p>${escapeHtml(truncate(row.use_case, 120))}</p>
      <div class="tag-cloud">${renderPlainTags(splitSemicolon(row.concepts).slice(0, 6), "accent")}</div>
      <div class="rag-source-actions">
        <button class="secondary-button compact-button profile-button" type="button" data-thesis-id="${escapeHtml(row.thesis_id)}">View profile</button>
        <a class="pdf-link compact-link" href="${escapeHtml(row.pdf_url)}" target="_blank" rel="noreferrer">Open PDF</a>
      </div>
    </article>
  `;
}

function splitSemicolon(value) {
  return String(value || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderPlainTags(items, variant = "") {
  return items.map((item) => `<span class="tag ${variant}">${escapeHtml(item)}</span>`).join("");
}

function renderRagStatus(message, kind) {
  const status = qs("#rag-status");
  status.textContent = message;
  status.className = `status-banner ${kind || "muted"}-banner`;
}

function setRagBusy(isBusy) {
  state.ragBusy = isBusy;
  const showAll = qs("#rag-show-all").checked;
  qs("#rag-ask-button").disabled = isBusy;
  qs("#rag-question").disabled = isBusy;
  qs("#rag-top-k").disabled = isBusy || showAll;
  qs("#rag-use-llm").disabled = isBusy;
  qs("#rag-show-all").disabled = isBusy;
  if (isBusy) {
    qs("#rag-previous-page-button").disabled = true;
    qs("#rag-next-page-button").disabled = true;
  } else {
    const canPaginate = state.ragAllResults && state.ragTotalPages > 1;
    qs("#rag-previous-page-button").disabled = !canPaginate || !state.ragHasPrevious;
    qs("#rag-next-page-button").disabled = !canPaginate || !state.ragHasNext;
  }
}

function syncRagControls() {
  const showAll = qs("#rag-show-all").checked;
  qs("#rag-top-k").disabled = showAll || state.ragBusy;
  if (!showAll) {
    state.ragAllResults = false;
    renderRagPagination({ total_pages: 0 });
  }
}

async function openThesisProfile(thesisId) {
  const modal = qs("#profile-modal");
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  qs("#profile-title").textContent = "Thesis Profile";
  qs("#profile-meta").textContent = thesisId;
  qs("#profile-body").innerHTML = '<div class="empty-state">Loading profile...</div>';
  try {
    const detail = await api.get(`/api/theses/${encodeURIComponent(thesisId)}`);
    renderThesisProfile(detail);
  } catch (error) {
    qs("#profile-body").innerHTML = `<div class="status-banner error-banner">${escapeHtml(error.message)}</div>`;
  }
}

function closeThesisProfile() {
  qs("#profile-modal").classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function renderThesisProfile(detail) {
  qs("#profile-title").textContent = detail.title || "Thesis Profile";
  qs("#profile-meta").textContent = [detail.thesis_id, detail.year, detail.master_level, detail.track].filter(Boolean).join(" | ");
  const concepts = detail.graph?.concepts || [];
  const keywords = detail.graph?.keywords || [];
  const similar = detail.similar_theses || [];
  qs("#profile-body").innerHTML = `
    <div class="profile-meta-grid">
      <div><span>Thesis ID</span><strong>${escapeHtml(detail.thesis_id)}</strong></div>
      <div><span>Year</span><strong>${escapeHtml(detail.year || "N/A")}</strong></div>
      <div><span>Level</span><strong>${escapeHtml(detail.master_level || "N/A")}</strong></div>
      <div><span>Track</span><strong>${escapeHtml(detail.track || "N/A")}</strong></div>
    </div>
    <div class="detail-section">
      <h4>Use case</h4>
      <p>${escapeHtml(detail.use_case)}</p>
    </div>
    <div class="detail-section">
      <h4>Methodology</h4>
      <p>${escapeHtml(detail.methodology)}</p>
    </div>
    <div class="detail-section">
      <h4>Concepts</h4>
      <div class="tag-cloud">${renderTags(concepts.slice(0, 16), "accent")}</div>
    </div>
    <div class="detail-section">
      <h4>Keywords</h4>
      <div class="tag-cloud">${renderTags(keywords.slice(0, 18))}</div>
    </div>
    <div class="detail-section">
      <h4>Similar theses</h4>
      <div class="mini-list">
        ${similar.map(renderSimilarRow).join("") || '<div class="muted">No related theses found.</div>'}
      </div>
    </div>
    <a class="pdf-link" href="/api/files/${encodeURIComponent(detail.thesis_id)}" target="_blank" rel="noreferrer">Open PDF</a>
  `;
}

async function runSearch({ page = state.searchPage } = {}) {
  const params = new URLSearchParams();
  const textQuery = qs("#text-query").value.trim();
  const concept = qs("#concept-filter").value;
  const year = qs("#year-filter").value;
  const level = qs("#level-filter").value;
  const track = qs("#track-filter").value;
  const requestedPage = Math.max(1, Number.isFinite(Number(page)) ? Math.trunc(Number(page)) : 1);

  if (concept) params.append("concept", concept);
  if (year) params.set("year", year);
  if (level) params.set("master_level", level);
  if (track) params.set("track", track);
  if (!concept && !year && !level && !track && textQuery) params.set("q", textQuery);
  params.set("match", "all");
  params.set("page", String(requestedPage));
  params.set("page_size", String(state.searchPageSize));

  const payload = await api.get(`/api/theses/page?${params.toString()}`);
  state.searchPage = payload.page || requestedPage;
  state.searchTotal = payload.total || 0;
  state.searchTotalPages = payload.total_pages || 0;
  renderThesisTable(payload.rows || []);
  renderSearchPagination(payload);
}

function clearSearch() {
  qs("#text-query").value = "";
  qs("#concept-filter").value = "";
  qs("#year-filter").value = "";
  qs("#level-filter").value = "";
  qs("#track-filter").value = "";
  state.selectedThesisId = null;
  qs("#detail-panel").innerHTML = '<div class="empty-state">Select a thesis to inspect its graph profile.</div>';
  runSearch({ page: 1 });
}

function showAllSearchResults() {
  qs("#text-query").value = "";
  qs("#concept-filter").value = "";
  qs("#year-filter").value = "";
  qs("#level-filter").value = "";
  qs("#track-filter").value = "";
  state.selectedThesisId = null;
  qs("#detail-panel").innerHTML = '<div class="empty-state">Select a thesis to inspect its graph profile.</div>';
  runSearch({ page: 1 });
}

function renderThesisTable(rows) {
  const first = state.searchTotal ? (state.searchPage - 1) * state.searchPageSize + 1 : 0;
  const last = state.searchTotal ? Math.min(state.searchPage * state.searchPageSize, state.searchTotal) : 0;
  qs("#result-count").textContent = `${formatNumber(state.searchTotal)} results | ${formatNumber(first)}-${formatNumber(last)} shown`;
  qs("#thesis-table").innerHTML = rows
    .map((row) => `
      <tr data-thesis-id="${escapeHtml(row.thesis_id)}" class="${row.thesis_id === state.selectedThesisId ? "selected" : ""}">
        <td>${escapeHtml(row.thesis_id)}</td>
        <td class="title-cell">${escapeHtml(row.title)}</td>
        <td>${escapeHtml(row.year)}</td>
        <td>${escapeHtml(row.master_level)}</td>
        <td>${escapeHtml(row.track)}</td>
        <td>${escapeHtml(truncate(row.use_case, 52))}</td>
      </tr>
    `)
    .join("");

  qsa("#thesis-table tr").forEach((row) => {
    row.addEventListener("click", () => loadThesisDetail(row.dataset.thesisId));
  });
}

function renderSearchPagination(payload) {
  const page = payload.page || 1;
  const totalPages = payload.total_pages || 0;
  qs("#pagination-status").textContent = totalPages
    ? `Page ${formatNumber(page)} of ${formatNumber(totalPages)} | ${formatNumber(payload.page_size || state.searchPageSize)} per page`
    : "No pages";
  qs("#previous-page-button").disabled = !payload.has_previous;
  qs("#next-page-button").disabled = !payload.has_next;
}

async function loadThesisDetail(thesisId) {
  state.selectedThesisId = thesisId;
  qsa("#thesis-table tr").forEach((row) => row.classList.toggle("selected", row.dataset.thesisId === thesisId));
  const detail = await api.get(`/api/theses/${encodeURIComponent(thesisId)}?similar_limit=8`);
  qs("#detail-panel").innerHTML = renderThesisDetail(detail);
}

function renderThesisDetail(detail) {
  const concepts = detail.graph?.concepts || [];
  const keywords = detail.graph?.keywords || [];
  const similar = detail.similar_theses || [];
  return `
    <h3 class="detail-title">${escapeHtml(detail.title)}</h3>
    <div class="detail-meta">
      <span class="tag accent">${escapeHtml(detail.thesis_id)}</span>
      <span class="tag">${escapeHtml(detail.year)}</span>
      <span class="tag">${escapeHtml(detail.master_level)}</span>
      <span class="tag">${escapeHtml(detail.track)}</span>
    </div>
    <div class="detail-section">
      <h4>Use case</h4>
      <p>${escapeHtml(detail.use_case)}</p>
    </div>
    <div class="detail-section">
      <h4>Methodology</h4>
      <p>${escapeHtml(detail.methodology)}</p>
    </div>
    <div class="detail-section">
      <h4>Concepts</h4>
      <div class="tag-cloud">${renderTags(concepts.slice(0, 12), "accent")}</div>
    </div>
    <div class="detail-section">
      <h4>Keywords</h4>
      <div class="tag-cloud">${renderTags(keywords.slice(0, 12))}</div>
    </div>
    <div class="detail-section">
      <h4>Similar theses</h4>
      <div class="mini-list">
        ${similar.map(renderSimilarRow).join("") || '<div class="muted">No related theses found.</div>'}
      </div>
    </div>
    <a class="pdf-link" href="/api/files/${encodeURIComponent(detail.thesis_id)}" target="_blank" rel="noreferrer">Open PDF</a>
  `;
}

function renderTags(items, variant = "") {
  return items.map((item) => `<span class="tag ${variant}">${escapeHtml(item.label)}</span>`).join("");
}

function renderSimilarRow(row) {
  return `
    <div class="mini-row">
      <strong>${escapeHtml(row.thesis_id)} | ${escapeHtml(truncate(row.title, 88))}</strong>
      <span>${escapeHtml(row.year)} | ${escapeHtml(row.master_level)} | ${escapeHtml(row.shared_concepts?.join("; ") || "")}</span>
    </div>
  `;
}

async function loadConceptIndex() {
  const concepts = state.facets?.concepts || (await api.get("/api/top/Concept?limit=60"));
  qs("#concept-list").innerHTML = concepts
    .map((concept) => `
      <button class="concept-item" type="button" data-concept="${escapeHtml(concept.label)}">
        <span class="concept-label">${escapeHtml(concept.label)}</span>
        <span class="rank-count">${formatNumber(concept.incoming_edges)}</span>
      </button>
    `)
    .join("");
  qsa(".concept-item").forEach((button) => {
    button.addEventListener("click", () => loadConceptDetail(button.dataset.concept));
  });
}

async function loadConceptDetail(label) {
  state.selectedConcept = label;
  qsa(".concept-item").forEach((button) => button.classList.toggle("active", button.dataset.concept === label));
  const detail = await api.get(`/api/concepts/${encodeURIComponent(label)}?limit=12`);
  qs("#concept-detail").innerHTML = renderConceptDetail(detail);
}

function renderConceptDetail(detail) {
  const conceptLabel = detail.concept?.label || state.selectedConcept;
  return `
    <h3 class="detail-title">${escapeHtml(conceptLabel)}</h3>
    <div class="detail-section">
      <h4>Connected theses</h4>
      <div class="mini-list">
        ${(detail.theses || []).map((row) => `
          <div class="mini-row">
            <strong>${escapeHtml(row.thesis_id)} | ${escapeHtml(truncate(row.title, 92))}</strong>
            <span>${escapeHtml(row.year)} | ${escapeHtml(row.master_level)} | ${escapeHtml(row.use_case)}</span>
          </div>
        `).join("")}
      </div>
    </div>
    <div class="detail-section">
      <h4>Related concepts</h4>
      <div class="tag-cloud">
        ${(detail.related_concepts || []).map((item) => `
          <span class="tag accent">${escapeHtml(item.label)} | ${formatNumber(item.shared_theses)}</span>
        `).join("")}
      </div>
    </div>
  `;
}

function updateFileLabel() {
  const files = [...qs("#pdf-file").files];
  if (files.length === 0) {
    qs("#file-label").textContent = "Choose one or more PDF theses";
  } else if (files.length === 1) {
    qs("#file-label").textContent = files[0].name;
  } else {
    qs("#file-label").textContent = `${files.length} PDF theses selected`;
  }
}

async function uploadImport(event) {
  event.preventDefault();
  const files = [...qs("#pdf-file").files];
  if (files.length === 0) {
    renderImportStatus("Select at least one PDF file first.", "warning");
    return;
  }
  renderImportStatus(`Processing ${files.length} PDF${files.length > 1 ? "s" : ""}...`, "working");
  setImportBusy(true);
  try {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    const result = await api.postForm("/api/imports/batch", formData);
    state.importItems = (result.results || []).map(createImportItem);
    state.selectedImportIndex = -1;
    state.currentDraft = null;
    state.llmSuggestions = null;
    renderBatchList();
    const nextIndex = findNextPendingImportIndex();
    if (nextIndex >= 0) {
      selectImportItem(nextIndex, false);
      renderImportStatus(importBatchSummary(result), result.errors_count ? "warning" : "success");
    } else {
      renderReviewEmpty();
      renderImportStatus(importBatchSummary(result), result.errors_count ? "error" : "warning");
    }
  } catch (error) {
    renderImportStatus(error.message, "error");
  } finally {
    setImportBusy(false);
  }
}

function createImportItem(result, index) {
  return {
    id: result.draft?.draft_id || `${result.status}-${index}-${result.file_name}`,
    file_name: result.file_name || result.draft?.original_file_name || `upload_${index + 1}.pdf`,
    status: result.status,
    reviewStatus: result.status === "draft" ? "pending" : result.status,
    duplicate: result.duplicate || null,
    draft: result.draft || null,
    error: result.error || null,
    llmSuggestions: null,
  };
}

function importBatchSummary(result) {
  const total = result.total ?? state.importItems.length;
  const drafts = result.drafts_count ?? state.importItems.filter((item) => item.status === "draft").length;
  const duplicates = result.duplicates_count ?? state.importItems.filter((item) => item.status === "duplicate").length;
  const errors = result.errors_count ?? state.importItems.filter((item) => item.status === "error").length;
  return `${total} PDF${total === 1 ? "" : "s"} processed: ${drafts} draft${drafts === 1 ? "" : "s"}, ${duplicates} duplicate${duplicates === 1 ? "" : "s"}, ${errors} error${errors === 1 ? "" : "s"}.`;
}

function renderBatchList() {
  const list = qs("#batch-list");
  if (!state.importItems.length) {
    list.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  list.classList.remove("hidden");
  list.innerHTML = state.importItems
    .map((item, index) => {
      const pending = isPendingDraft(item);
      const active = index === state.selectedImportIndex;
      const label = importItemStatusLabel(item);
      const detail = importItemDetail(item);
      return `
        <button
          class="batch-item ${active ? "active" : ""}"
          type="button"
          data-index="${index}"
          data-disabled="${pending ? "false" : "true"}"
          ${state.importBusy || !pending ? "disabled" : ""}
        >
          <span class="batch-file">${escapeHtml(item.file_name)}</span>
          <span class="batch-meta">${escapeHtml(detail)}</span>
          <span class="batch-status ${escapeHtml(importItemStatusKind(item))}">${escapeHtml(label)}</span>
        </button>
      `;
    })
    .join("");
  qsa(".batch-item").forEach((button) => {
    button.addEventListener("click", () => selectImportItem(Number(button.dataset.index)));
  });
}

function importItemStatusLabel(item) {
  if (item.reviewStatus === "approved") return "Approved";
  if (item.reviewStatus === "discarded") return "Discarded";
  if (item.status === "duplicate") return "Duplicate";
  if (item.status === "error") return "Error";
  if (item.draft?.needs_review) return "Needs review";
  return "Draft";
}

function importItemStatusKind(item) {
  if (item.reviewStatus === "approved") return "success";
  if (item.reviewStatus === "discarded") return "muted";
  if (item.status === "duplicate") return "warning";
  if (item.status === "error") return "error";
  if (item.draft?.needs_review) return "warning";
  return "success";
}

function importItemDetail(item) {
  if (item.status === "duplicate") {
    const duplicate = item.duplicate || {};
    return `Already imported as ${duplicate.thesis_id || duplicate.draft_id || "another item"}`;
  }
  if (item.status === "error") return item.error || "Import failed";
  const fields = item.draft?.fields || {};
  return fields.thesis_id ? `${fields.thesis_id} | ${fields.year || "N/A"}` : "Ready for review";
}

function isPendingDraft(item) {
  return item?.status === "draft" && item.reviewStatus === "pending";
}

function findNextPendingImportIndex(afterIndex = -1) {
  for (let index = afterIndex + 1; index < state.importItems.length; index += 1) {
    if (isPendingDraft(state.importItems[index])) return index;
  }
  for (let index = 0; index <= afterIndex; index += 1) {
    if (isPendingDraft(state.importItems[index])) return index;
  }
  return -1;
}

function selectImportItem(index, showStatus = true) {
  const item = state.importItems[index];
  if (!isPendingDraft(item)) return;
  saveCurrentReviewEdits();
  state.selectedImportIndex = index;
  state.currentDraft = item.draft;
  state.llmSuggestions = item.llmSuggestions;
  renderBatchList();
  renderImportReview(item.draft, item.llmSuggestions);
  if (showStatus) {
    renderImportStatus(`Reviewing ${item.file_name}.`, item.draft.needs_review ? "warning" : "success");
  }
}

function saveCurrentReviewEdits() {
  if (!state.currentDraft || qs("#review-form").classList.contains("hidden")) return;
  state.currentDraft.fields = { ...state.currentDraft.fields, ...collectReviewFields() };
  const index = state.importItems.findIndex((item) => item.draft?.draft_id === state.currentDraft.draft_id);
  if (index >= 0) {
    state.importItems[index].draft = state.currentDraft;
  }
}

function renderImportReview(draft, llmSuggestions = null) {
  const fields = draft.fields || {};
  qs("#review-empty").classList.add("hidden");
  qs("#review-form").classList.remove("hidden");
  qs("#draft-meta").textContent = `${draft.original_file_name} | ${draft.pages_count} pages | confidence ${draft.extraction_confidence}`;
  setValue("#review-thesis-id", fields.thesis_id);
  setValue("#review-title", fields.title);
  setValue("#review-year", fields.year || "N/A");
  setValue("#review-master-level", fields.master_level || "N/A");
  setValue("#review-track", fields.track || "N/A");
  setValue("#review-keywords", fields.keywords);
  setValue("#review-concepts", fields.concepts);
  setValue("#review-use-case", fields.use_case);
  setValue("#review-methodology", fields.methodology);
  setValue("#review-abstract", fields.abstract);
  renderLlmSuggestions(llmSuggestions || draft.llm_review?.suggestions || null);
}

function renderReviewEmpty() {
  qs("#review-form").classList.add("hidden");
  qs("#review-empty").classList.remove("hidden");
  qs("#draft-meta").textContent = "";
  state.llmSuggestions = null;
  renderLlmSuggestions(null);
}

async function approveCurrentImport() {
  if (!state.currentDraft) {
    renderImportStatus("No draft selected.", "warning");
    return;
  }
  const approvedIndex = state.selectedImportIndex;
    renderImportStatus("Approving and rebuilding graph/RAG outputs...", "working");
  setImportBusy(true);
  try {
    const result = await api.postJson(`/api/imports/${encodeURIComponent(state.currentDraft.draft_id)}/approve`, collectReviewFields());
    markImportItemHandled(approvedIndex, "approved", result);
    state.currentDraft = null;
    state.llmSuggestions = null;
    renderBatchList();
    await refreshAll();
    if (selectNextPendingImport(approvedIndex, false)) {
      renderImportStatus(`Approved ${result.thesis_id}. Next draft selected. Database, CSV, graph, and RAG are updated.`, "success");
    } else {
      renderImportStatus(`Approved ${result.thesis_id}. Database, CSV, graph, and RAG are updated.`, "success");
      renderReviewEmpty();
      qs("#pdf-file").value = "";
      updateFileLabel();
    }
  } catch (error) {
    renderImportStatus(error.message, "error");
  } finally {
    setImportBusy(false);
  }
}

async function discardCurrentImport() {
  if (!state.currentDraft) {
    renderImportStatus("No draft selected.", "warning");
    return;
  }
  const discardedIndex = state.selectedImportIndex;
  renderImportStatus("Discarding draft...", "working");
  setImportBusy(true);
  try {
    await api.delete(`/api/imports/${encodeURIComponent(state.currentDraft.draft_id)}`);
    markImportItemHandled(discardedIndex, "discarded");
    state.currentDraft = null;
    state.llmSuggestions = null;
    renderBatchList();
    if (selectNextPendingImport(discardedIndex, false)) {
      renderImportStatus("Draft discarded. Next draft selected.", "success");
    } else {
      renderImportStatus("Draft discarded.", "success");
      renderReviewEmpty();
      qs("#pdf-file").value = "";
      updateFileLabel();
    }
  } catch (error) {
    renderImportStatus(error.message, "error");
  } finally {
    setImportBusy(false);
  }
}

function markImportItemHandled(index, reviewStatus, result = null) {
  if (index < 0 || !state.importItems[index]) return;
  state.importItems[index].reviewStatus = reviewStatus;
  state.importItems[index].result = result;
}

function selectNextPendingImport(afterIndex, showStatus = true) {
  const nextIndex = findNextPendingImportIndex(afterIndex);
  if (nextIndex < 0) {
    state.selectedImportIndex = -1;
    renderBatchList();
    return false;
  }
  selectImportItem(nextIndex, showStatus);
  return true;
}

async function generateLlmSuggestions() {
  if (!state.currentDraft) {
    renderImportStatus("No draft selected.", "warning");
    return;
  }
  renderImportStatus("Generating LLM suggestions with local Ollama...", "working");
  setImportBusy(true);
  try {
    const result = await api.postJson(`/api/imports/${encodeURIComponent(state.currentDraft.draft_id)}/llm-suggestions`, {
      fields: collectReviewFields(),
    });
    if (result.status === "unavailable") {
      renderLlmSuggestions(null);
      renderImportStatus("LLM unavailable. You can still review and approve manually.", "warning");
      return;
    }
    state.llmSuggestions = result;
    const index = state.importItems.findIndex((item) => item.draft?.draft_id === state.currentDraft.draft_id);
    if (index >= 0) state.importItems[index].llmSuggestions = result;
    renderLlmSuggestions(result);
    renderImportStatus("LLM suggestions ready. Review before applying.", "success");
  } catch (error) {
    renderImportStatus(error.message, "error");
  } finally {
    setImportBusy(false);
  }
}

function applyLlmSuggestions() {
  if (!state.llmSuggestions?.suggestions) {
    renderImportStatus("No LLM suggestions available.", "warning");
    return;
  }
  const fields = state.llmSuggestions.suggestions;
  const mapping = {
    thesis_id: "#review-thesis-id",
    title: "#review-title",
    year: "#review-year",
    master_level: "#review-master-level",
    track: "#review-track",
    keywords: "#review-keywords",
    concepts: "#review-concepts",
    use_case: "#review-use-case",
    methodology: "#review-methodology",
    abstract: "#review-abstract",
  };
  Object.entries(mapping).forEach(([field, selector]) => {
    if (fields[field]) setValue(selector, fields[field]);
  });
  renderImportStatus("LLM suggestions applied to the review form. Approve only after checking them.", "success");
}

function renderLlmSuggestions(result) {
  const panel = qs("#llm-suggestion-panel");
  const applyButton = qs("#apply-llm-button");
  if (!result?.suggestions) {
    panel.classList.add("hidden");
    applyButton.classList.add("hidden");
    qs("#llm-suggestion-content").innerHTML = "";
    qs("#llm-confidence").textContent = "";
    qs("#llm-notes").textContent = "";
    return;
  }
  state.llmSuggestions = result;
  panel.classList.remove("hidden");
  applyButton.classList.remove("hidden");
  qs("#llm-confidence").textContent = `${result.model || "local model"} | confidence ${result.confidence ?? 0}`;
  qs("#llm-suggestion-content").innerHTML = Object.entries(result.suggestions)
    .filter(([, value]) => String(value ?? "").trim())
    .map(([field, value]) => `
      <div class="suggestion-item">
        <span>${escapeHtml(field.replaceAll("_", " "))}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `)
    .join("");
  qs("#llm-notes").textContent = result.notes || "Review every suggestion before approval.";
}

function collectReviewFields() {
  return {
    thesis_id: valueOf("#review-thesis-id"),
    title: valueOf("#review-title"),
    year: valueOf("#review-year"),
    master_level: valueOf("#review-master-level"),
    track: valueOf("#review-track"),
    abstract: valueOf("#review-abstract"),
    keywords: valueOf("#review-keywords"),
    concepts: valueOf("#review-concepts"),
    use_case: valueOf("#review-use-case"),
    methodology: valueOf("#review-methodology"),
  };
}

function renderImportStatus(message, kind) {
  const status = qs("#import-status");
  status.textContent = message;
  status.className = `status-banner ${kind || "muted"}-banner`;
}

function setImportBusy(isBusy) {
  state.importBusy = isBusy;
  qs("#process-upload-button").disabled = isBusy;
  qs("#approve-import-button").disabled = isBusy;
  qs("#discard-import-button").disabled = isBusy;
  qs("#generate-llm-button").disabled = isBusy;
  qs("#apply-llm-button").disabled = isBusy;
  qsa(".batch-item").forEach((button) => {
    button.disabled = isBusy || button.dataset.disabled === "true";
  });
}

function setValue(selector, value) {
  qs(selector).value = value ?? "";
}

function valueOf(selector) {
  return qs(selector).value.trim();
}

init().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<pre class="fatal-error">${escapeHtml(error.message)}</pre>`;
});

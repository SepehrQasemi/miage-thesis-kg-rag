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
  graphMap: null,
  graphMapRaw: null,
  graphSelectedNodeTypes: [],
  graphFocusType: "Thesis",
  graphFilters: {
    relationType: "",
    concept: "",
    useCase: "",
    year: "",
    masterLevel: "",
    track: "",
    selectedOnly: false,
    analysisLinks: false,
    analysisPair: "Year:Concept",
  },
  graphBusy: false,
  selectedGraphNodeId: null,
  graphAnimationFrame: null,
  graphZoom: {
    scale: 1,
    x: 0,
    y: 0,
  },
};

const viewTitles = {
  dashboard: ["Dashboard", "Overview of the extracted thesis graph."],
  graph: ["Knowledge Graph", "Explore how theses connect to concepts, use cases, methods, years, levels, and tracks."],
  search: ["Thesis Search", "Search and filter thesis metadata through graph relations."],
  concepts: ["Concepts", "Explore frequent concepts and their connected theses."],
  dataset: ["Dataset CSV", "View every extracted thesis row in one table."],
  rag: ["Ask / RAG", "Ask questions over local thesis metadata and cited sources."],
  import: ["Import PDFs", "Add one or more theses through extraction, review, and approval."],
  help: ["Help", "Use the app safely and understand the main workflows."],
};

const graphTypeColors = {
  Thesis: "#1d6f8f",
  Concept: "#d8643f",
  Keyword: "#7a8797",
  UseCase: "#247a5a",
  Methodology: "#7a5fb5",
  Year: "#a67c00",
  MasterLevel: "#3d647d",
  Track: "#0f766e",
};

const graphTypeLabels = {
  Thesis: "Thesis",
  Concept: "Concept",
  Keyword: "Keyword",
  UseCase: "Use case",
  Methodology: "Methodology",
  Year: "Year",
  MasterLevel: "Level",
  Track: "Track",
};

const GRAPH_TITLE_LABEL_THRESHOLD = 20;
const GRAPH_ZOOM_MIN = 0.45;
const GRAPH_ZOOM_MAX = 3;
const GRAPH_ZOOM_STEP = 1.2;
const GRAPH_ANALYSIS_NODE_TYPES = new Set(["Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"]);
const GRAPH_ANALYSIS_NODE_ORDER = {
  Year: 0,
  MasterLevel: 1,
  Track: 2,
  Concept: 3,
  Keyword: 4,
  UseCase: 5,
  Methodology: 6,
};
const GRAPH_ANALYSIS_LINK_LIMIT = 180;

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

function formatScore(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(3) : "N/A";
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
  qs("#graph-load-button").addEventListener("click", loadGraphMap);
  qs("#graph-reload-button").addEventListener("click", loadGraphMap);
  qs("#graph-focus-type").addEventListener("change", handleGraphFocusChange);
  qsa(".graph-category-checkbox").forEach((input) => {
    input.addEventListener("change", handleGraphCategoryChange);
  });
  qs("#graph-zoom-in").addEventListener("click", () => zoomGraphBy(GRAPH_ZOOM_STEP));
  qs("#graph-zoom-out").addEventListener("click", () => zoomGraphBy(1 / GRAPH_ZOOM_STEP));
  qs("#graph-zoom-reset").addEventListener("click", resetGraphZoom);
  bindGraphViewportInteractions(qs("#knowledge-graph-svg"));
  [
    "#graph-relation-filter",
    "#graph-concept-filter",
    "#graph-use-case-filter",
    "#graph-year-filter",
    "#graph-level-filter",
    "#graph-track-filter",
    "#graph-analysis-pair",
  ].forEach((selector) => {
    qs(selector).addEventListener("change", applyGraphFilterControls);
  });
  qs("#graph-selected-only").addEventListener("change", applyGraphFilterControls);
  qs("#graph-analysis-links").addEventListener("change", applyGraphFilterControls);
  qs("#graph-clear-filters-button").addEventListener("click", clearGraphFilters);
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
  if (view === "graph" && !state.graphMapRaw && !state.graphBusy) {
    renderGraphSetupPrompt();
  }
}

async function refreshAll() {
  state.graphMap = null;
  state.graphMapRaw = null;
  state.graphSelectedNodeTypes = [];
  state.selectedGraphNodeId = null;
  await Promise.all([loadDashboard(), loadFacets(), loadDataset()]);
  await runSearch({ page: 1 });
  await loadConceptIndex();
  if (state.view === "graph") {
    renderGraphSetupPrompt();
  }
}

async function loadDashboard() {
  const summary = await api.get("/api/summary");
  renderGraphBackend(summary.backend);
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

function renderGraphBackend(backend) {
  qs("#graph-backend-label").textContent = backend === "neo4j" ? "Local Neo4j graph" : "Graph backend";
}

async function loadGraphMap() {
  const focusType = selectedGraphFocusType();
  const nodeTypes = selectedGraphNodeTypes();
  if (!nodeTypes.length) {
    state.graphMap = null;
    state.graphMapRaw = null;
    state.graphSelectedNodeTypes = [];
    renderGraphSetupPrompt("Select at least one category before loading the graph.", "error");
    return;
  }
  setGraphBusy(true);
  renderGraphModeControls(focusType);
  renderGraphMapStatus(`Loading ${graphTypeLabel(focusType)}-centered graph with ${nodeTypes.map(graphTypeLabel).join(", ")}...`, "working");
  try {
    const params = new URLSearchParams({ node_types: nodeTypes.join(","), focus_type: focusType });
    const payload = await api.get(`/api/graph/map?${params.toString()}`);
    state.graphMapRaw = payload;
    state.graphSelectedNodeTypes = nodeTypes;
    state.graphFocusType = focusType;
    state.selectedGraphNodeId = null;
    fillGraphFilterSelects();
    renderFilteredGraphMap();
  } catch (error) {
    renderGraphMapStatus(`Graph map failed: ${error.message}`, "error");
    qs("#knowledge-graph-svg").innerHTML = "";
    qs("#graph-inspector").innerHTML = `<h3>Graph Inspector</h3><div class="status-banner error-banner">${escapeHtml(error.message)}</div>`;
  } finally {
    setGraphBusy(false);
  }
}

function selectedGraphNodeTypes() {
  const nodeTypes = qsa(".graph-category-checkbox:checked").map((input) => input.value);
  const focusType = selectedGraphFocusType();
  if (!nodeTypes.includes(focusType)) {
    nodeTypes.unshift(focusType);
  }
  return nodeTypes;
}

function selectedGraphFocusType() {
  return valueOf("#graph-focus-type") || "Thesis";
}

function handleGraphFocusChange() {
  const focusType = selectedGraphFocusType();
  syncGraphFocusCheckbox(focusType);
  renderGraphModeControls(focusType);
  handleGraphCategoryChange();
}

function handleGraphCategoryChange() {
  syncGraphFocusCheckbox();
  updateGraphCategorySummary();
  if (state.view !== "graph" || state.graphBusy) return;
  if (state.graphMapRaw) {
    renderGraphMapStatus("Graph categories changed. Click Load graph to refresh the map.", "muted");
  } else {
    renderGraphSetupPrompt();
  }
}

function syncGraphFocusCheckbox(focusType = selectedGraphFocusType()) {
  const focusCheckbox = qsa(".graph-category-checkbox").find((input) => input.value === focusType);
  if (focusCheckbox) focusCheckbox.checked = true;
}

function renderGraphModeControls(focusType = selectedGraphFocusType()) {
  const metadataMode = focusType !== "Thesis";
  const analysisToggle = qs("#graph-analysis-links");
  const analysisPair = qs("#graph-analysis-pair");
  analysisToggle.disabled = metadataMode || state.graphBusy;
  analysisPair.disabled = metadataMode || state.graphBusy;
  if (metadataMode) {
    analysisToggle.checked = false;
    state.graphFilters.analysisLinks = false;
  }
}

function updateGraphCategorySummary() {
  const selected = selectedGraphNodeTypes();
  const focusType = selectedGraphFocusType();
  const summary = qs("#graph-category-summary");
  if (!summary) return;
  summary.textContent = selected.length
    ? `${graphTypeLabel(focusType)} center | ${selected.length} selected: ${selected.map(graphTypeLabel).join(", ")}`
    : "No category selected";
}

function renderGraphSetupPrompt(message = "Select graph categories, then click Load graph.", kind = "muted") {
  if (state.graphAnimationFrame) {
    cancelAnimationFrame(state.graphAnimationFrame);
    state.graphAnimationFrame = null;
  }
  state.graphMap = null;
  updateGraphCategorySummary();
  renderGraphMapStatus(message, kind);
  qs("#knowledge-graph-svg").innerHTML = "";
  qs("#graph-legend").innerHTML = "";
  renderGraphInspector(null);
  applyGraphZoomTransform();
}

function graphMapSummary(payload) {
  const stats = payload.stats || {};
  const backendLabel = payload.backend === "neo4j" ? "Neo4j" : "Graph";
  const visibleCounts = stats.visible_node_counts || {};
  const focusLabel = graphTypeLabel(stats.focus_type || "Thesis");
  if (stats.graph_mode === "metadata_focus") {
    const categoryText = (stats.selected_node_types || []).length
      ? ` | categories: ${stats.selected_node_types.map(graphTypeLabel).join(", ")}`
      : "";
    const filterText = stats.filters_active ? ` | ${formatNumber(stats.filters_active)} active filter${stats.filters_active === 1 ? "" : "s"}` : "";
    const directText = stats.direct_relation_edges
      ? ` | ${formatNumber(stats.direct_relation_edges)} direct ${stats.direct_relation_edges === 1 ? "relation" : "relations"}`
      : "";
    const thesisText = stats.thesis_relation_edges
      ? ` | ${formatNumber(stats.thesis_relation_edges)} thesis ${stats.thesis_relation_edges === 1 ? "link" : "links"}`
      : "";
    return `${focusLabel}-centered map, ${formatNumber(stats.visible_nodes || 0)} nodes, ${formatNumber(stats.visible_edges || 0)} relations from ${formatNumber(stats.source_documents || 0)} total theses | ${backendLabel}${categoryText}${filterText}${directText}${thesisText}`;
  }
  const thesisCount = visibleCounts.Thesis || 0;
  const categoryText = (stats.selected_node_types || []).length
    ? ` | categories: ${stats.selected_node_types.map(graphTypeLabel).join(", ")}`
    : "";
  const filterText = stats.filters_active ? ` | ${formatNumber(stats.filters_active)} active filter${stats.filters_active === 1 ? "" : "s"}` : "";
  const analysisText = stats.analysis_edges
    ? ` | ${stats.analysis_edges_total > stats.analysis_edges ? `${formatNumber(stats.analysis_edges)} of ${formatNumber(stats.analysis_edges_total)}` : formatNumber(stats.analysis_edges)} analysis links`
    : "";
  return `${formatNumber(thesisCount)} theses in map, ${formatNumber(stats.visible_nodes || 0)} nodes, ${formatNumber(stats.visible_edges || 0)} relations from ${formatNumber(stats.source_documents || 0)} total theses | ${backendLabel}${categoryText}${filterText}${analysisText}`;
}

function renderGraphMapStatus(message, kind = "muted") {
  const status = qs("#graph-map-status");
  status.textContent = message;
  status.className = `status-banner ${kind}-banner compact-status`;
}

function setGraphBusy(isBusy) {
  state.graphBusy = isBusy;
  qs("#graph-load-button").disabled = isBusy;
  qs("#graph-reload-button").disabled = isBusy;
  qs("#graph-focus-type").disabled = isBusy;
  qsa(".graph-category-checkbox").forEach((input) => {
    input.disabled = isBusy;
  });
  qsa("#graph-zoom-in, #graph-zoom-out, #graph-zoom-reset").forEach((button) => {
    button.disabled = isBusy;
  });
  qsa(".graph-filter-panel select, .graph-filter-panel input, #graph-clear-filters-button").forEach((element) => {
    element.disabled = isBusy;
  });
  renderGraphModeControls();
}

function defaultGraphFilters() {
  return {
    relationType: "",
    concept: "",
    useCase: "",
    year: "",
    masterLevel: "",
    track: "",
    selectedOnly: false,
    analysisLinks: false,
    analysisPair: "Year:Concept",
  };
}

function readGraphFiltersFromControls() {
  return {
    relationType: valueOf("#graph-relation-filter"),
    concept: valueOf("#graph-concept-filter"),
    useCase: valueOf("#graph-use-case-filter"),
    year: valueOf("#graph-year-filter"),
    masterLevel: valueOf("#graph-level-filter"),
    track: valueOf("#graph-track-filter"),
    selectedOnly: qs("#graph-selected-only").checked,
    analysisLinks: qs("#graph-analysis-links").checked,
    analysisPair: valueOf("#graph-analysis-pair") || "Year:Concept",
  };
}

function applyGraphFilterControls() {
  state.graphFilters = readGraphFiltersFromControls();
  renderFilteredGraphMap();
}

function clearGraphFilters() {
  state.graphFilters = defaultGraphFilters();
  setValue("#graph-relation-filter", "");
  setValue("#graph-concept-filter", "");
  setValue("#graph-use-case-filter", "");
  setValue("#graph-year-filter", "");
  setValue("#graph-level-filter", "");
  setValue("#graph-track-filter", "");
  setValue("#graph-analysis-pair", "Year:Concept");
  qs("#graph-selected-only").checked = false;
  qs("#graph-analysis-links").checked = false;
  renderFilteredGraphMap();
}

function renderFilteredGraphMap() {
  if (!state.graphMapRaw) return;
  const selectedBeforeRender = state.selectedGraphNodeId;
  const filteredPayload = filterGraphMap(state.graphMapRaw, state.graphFilters, selectedBeforeRender);
  const selectedStillDisplayed = selectedBeforeRender && filteredPayload.nodes.some((node) => node.id === selectedBeforeRender);
  state.selectedGraphNodeId = selectedStillDisplayed ? selectedBeforeRender : null;
  state.graphMap = filteredPayload;
  renderKnowledgeGraph(filteredPayload);
  renderGraphMapStatus(graphMapSummary(filteredPayload), "success");
  if (state.selectedGraphNodeId) {
    renderGraphSelection();
    renderGraphInspector(state.selectedGraphNodeId);
  }
}

function filterGraphMap(payload, filters, selectedNodeId) {
  if (payload.stats?.graph_mode === "metadata_focus") {
    return filterMetadataFocusGraphMap(payload, filters, selectedNodeId);
  }
  const rawNodes = payload.nodes || [];
  const rawEdges = payload.edges || [];
  const nodeById = new Map(rawNodes.map((node) => [node.id, node]));
  const analysisTypes = filters.analysisLinks ? graphAnalysisPairTypes(filters.analysisPair) : null;
  const thesisIds = new Set(
    rawNodes
      .filter((node) => node.type === "Thesis" && graphThesisMatchesFilters(node, rawEdges, nodeById, filters))
      .map((node) => node.id),
  );

  let visibleEdges = rawEdges.filter((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return false;
    const thesisNode = source.type === "Thesis" ? source : target.type === "Thesis" ? target : null;
    if (!thesisNode || !thesisIds.has(thesisNode.id)) return false;

    const otherNode = source.type === "Thesis" ? target : source;
    if (filters.relationType && otherNode.type !== filters.relationType) return false;
    if (analysisTypes && !analysisTypes.has(otherNode.type)) return false;

    const specificTargets = [
      filters.concept ? { type: "Concept", label: filters.concept } : null,
      filters.useCase ? { type: "UseCase", label: filters.useCase } : null,
    ].filter(Boolean);
    if (specificTargets.length && !filters.analysisLinks) {
      return specificTargets.some((targetFilter) => otherNode.type === targetFilter.type && otherNode.label === targetFilter.label);
    }

    return true;
  });

  if (filters.selectedOnly && selectedNodeId && nodeById.has(selectedNodeId)) {
    visibleEdges = visibleEdges.filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId);
  }

  const nodeIds = new Set();
  visibleEdges.forEach((edge) => {
    nodeIds.add(edge.source);
    nodeIds.add(edge.target);
  });

  const relationScoped = filters.relationType || filters.concept || filters.useCase || (filters.selectedOnly && selectedNodeId);
  if (!relationScoped) {
    thesisIds.forEach((nodeId) => nodeIds.add(nodeId));
  }
  if (filters.selectedOnly && selectedNodeId && nodeById.has(selectedNodeId)) {
    nodeIds.add(selectedNodeId);
  }

  const nodes = rawNodes.filter((node) => nodeIds.has(node.id));
  const baseEdges = visibleEdges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
  const analysisResult = filters.analysisLinks ? graphAnalysisEdges(rawEdges, nodeById, thesisIds, nodeIds, filters.analysisPair) : { edges: [], total: 0 };
  const analysisEdges = analysisResult.edges;
  const edges = [...baseEdges, ...analysisEdges];
  const visibleNodeCounts = nodes.reduce((counts, node) => {
    counts[node.type] = (counts[node.type] || 0) + 1;
    return counts;
  }, {});

  return {
    ...payload,
    nodes,
    edges,
    stats: {
      ...(payload.stats || {}),
      visible_nodes: nodes.length,
      visible_edges: edges.length,
      visible_node_counts: visibleNodeCounts,
      filters_active: graphFilterCount(filters),
      analysis_edges: analysisEdges.length,
      analysis_edges_total: analysisResult.total,
    },
  };
}

function filterMetadataFocusGraphMap(payload, filters, selectedNodeId) {
  const rawNodes = payload.nodes || [];
  const rawEdges = payload.edges || [];
  const nodeById = new Map(rawNodes.map((node) => [node.id, node]));
  let visibleEdges = rawEdges.filter((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return false;
    if (filters.relationType && source.type !== filters.relationType && target.type !== filters.relationType) return false;
    if (filters.concept && !graphEdgeHasEndpoint(source, target, "Concept", filters.concept)) return false;
    if (filters.useCase && !graphEdgeHasEndpoint(source, target, "UseCase", filters.useCase)) return false;
    if (filters.year && !graphEdgeHasEndpoint(source, target, "Year", filters.year)) return false;
    if (filters.masterLevel && !graphEdgeHasEndpoint(source, target, "MasterLevel", filters.masterLevel)) return false;
    if (filters.track && !graphEdgeHasEndpoint(source, target, "Track", filters.track)) return false;
    return true;
  });

  if (filters.selectedOnly && selectedNodeId && nodeById.has(selectedNodeId)) {
    visibleEdges = visibleEdges.filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId);
  }

  const nodeIds = new Set();
  visibleEdges.forEach((edge) => {
    nodeIds.add(edge.source);
    nodeIds.add(edge.target);
  });
  if (filters.selectedOnly && selectedNodeId && nodeById.has(selectedNodeId)) {
    nodeIds.add(selectedNodeId);
  }
  const nodes = rawNodes.filter((node) => nodeIds.has(node.id));
  const visibleNodeCounts = nodes.reduce((counts, node) => {
    counts[node.type] = (counts[node.type] || 0) + 1;
    return counts;
  }, {});
  const directRelationCount = visibleEdges.filter((edge) => edge.type === "DIRECT_RELATION").length;
  const thesisRelationCount = visibleEdges.length - directRelationCount;

  return {
    ...payload,
    nodes,
    edges: visibleEdges,
    stats: {
      ...(payload.stats || {}),
      visible_nodes: nodes.length,
      visible_edges: visibleEdges.length,
      visible_node_counts: visibleNodeCounts,
      filters_active: graphFilterCount(filters),
      analysis_edges: 0,
      analysis_edges_total: 0,
      direct_relation_edges: directRelationCount,
      thesis_relation_edges: thesisRelationCount,
    },
  };
}

function graphEdgeHasEndpoint(source, target, type, label) {
  return (source.type === type && source.label === label) || (target.type === type && target.label === label);
}

function graphAnalysisEdges(rawEdges, nodeById, thesisIds, visibleNodeIds, analysisPair) {
  const pairTypes = graphAnalysisPairTypes(analysisPair);
  const byThesis = new Map();
  rawEdges.forEach((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return;
    const thesisNode = source.type === "Thesis" ? source : target.type === "Thesis" ? target : null;
    if (!thesisNode || !thesisIds.has(thesisNode.id)) return;
    const metadataNode = source.type === "Thesis" ? target : source;
    if (!visibleNodeIds.has(metadataNode.id) || !GRAPH_ANALYSIS_NODE_TYPES.has(metadataNode.type)) return;
    if (!byThesis.has(thesisNode.id)) byThesis.set(thesisNode.id, []);
    byThesis.get(thesisNode.id).push(metadataNode.id);
  });

  const pairCounts = new Map();
  byThesis.forEach((metadataIds) => {
    const uniqueIds = [...new Set(metadataIds)].sort(compareGraphAnalysisNodeIds(nodeById));
    for (let left = 0; left < uniqueIds.length; left += 1) {
      for (let right = left + 1; right < uniqueIds.length; right += 1) {
        const sourceId = uniqueIds[left];
        const targetId = uniqueIds[right];
        if (pairTypes && !graphAnalysisPairMatches(nodeById.get(sourceId), nodeById.get(targetId), pairTypes)) continue;
        const key = `${sourceId}||${targetId}`;
        pairCounts.set(key, (pairCounts.get(key) || 0) + 1);
      }
    }
  });

  const edges = [...pairCounts.entries()].map(([key, weight]) => {
    const [source, target] = key.split("||");
    return {
      id: `analysis:${source}->${target}`,
      source,
      target,
      type: "ANALYSIS_LINK",
      weight,
    };
  });
  edges.sort((left, right) => {
    if (right.weight !== left.weight) return right.weight - left.weight;
    const leftSource = nodeById.get(left.source);
    const rightSource = nodeById.get(right.source);
    const sourceCompare = String(leftSource?.label || left.source).localeCompare(String(rightSource?.label || right.source), undefined, { numeric: true, sensitivity: "base" });
    if (sourceCompare !== 0) return sourceCompare;
    const leftTarget = nodeById.get(left.target);
    const rightTarget = nodeById.get(right.target);
    return String(leftTarget?.label || left.target).localeCompare(String(rightTarget?.label || right.target), undefined, { numeric: true, sensitivity: "base" });
  });
  return {
    edges: edges.slice(0, GRAPH_ANALYSIS_LINK_LIMIT),
    total: edges.length,
  };
}

function graphAnalysisPairTypes(analysisPair) {
  if (!analysisPair || analysisPair === "All") return null;
  const [leftType, rightType] = String(analysisPair).split(":");
  if (!leftType || !rightType) return null;
  return new Set([leftType, rightType]);
}

function graphAnalysisPairMatches(leftNode, rightNode, pairTypes) {
  return Boolean(leftNode && rightNode && pairTypes.has(leftNode.type) && pairTypes.has(rightNode.type) && leftNode.type !== rightNode.type);
}

function compareGraphAnalysisNodeIds(nodeById) {
  return (leftId, rightId) => {
    const left = nodeById.get(leftId);
    const right = nodeById.get(rightId);
    const leftOrder = GRAPH_ANALYSIS_NODE_ORDER[left?.type] ?? 99;
    const rightOrder = GRAPH_ANALYSIS_NODE_ORDER[right?.type] ?? 99;
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    return String(left?.label || leftId).localeCompare(String(right?.label || rightId), undefined, { numeric: true, sensitivity: "base" });
  };
}

function graphThesisMatchesFilters(node, edges, nodeById, filters) {
  const metadata = node.metadata || {};
  if (filters.year && String(metadata.year || "") !== filters.year) return false;
  if (filters.masterLevel && String(metadata.master_level || "") !== filters.masterLevel) return false;
  if (filters.track && String(metadata.track || "") !== filters.track) return false;
  if (filters.concept && !graphThesisHasTarget(node.id, edges, nodeById, "Concept", filters.concept)) return false;
  if (filters.useCase && !graphThesisHasTarget(node.id, edges, nodeById, "UseCase", filters.useCase)) return false;
  return true;
}

function graphThesisHasTarget(thesisNodeId, edges, nodeById, targetType, targetLabel) {
  return edges.some((edge) => {
    if (edge.source !== thesisNodeId && edge.target !== thesisNodeId) return false;
    const neighbourId = edge.source === thesisNodeId ? edge.target : edge.source;
    const neighbour = nodeById.get(neighbourId);
    return neighbour?.type === targetType && neighbour.label === targetLabel;
  });
}

function graphFilterCount(filters) {
  return Object.entries(filters).filter(([key, value]) => {
    if (key === "analysisLinks" || key === "analysisPair") return false;
    return key === "selectedOnly" ? value : Boolean(value);
  }).length;
}

function renderKnowledgeGraph(payload) {
  const svg = qs("#knowledge-graph-svg");
  const shell = qs(".graph-canvas-shell");
  const width = Math.max(720, Math.round(shell.clientWidth || 960));
  const height = Math.max(420, Math.round(shell.clientHeight || 620));
  const nodes = (payload.nodes || []).map((node, index) => ({
    ...node,
    index,
    radius: graphNodeRadius(node),
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
  }));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const visibleThesisCount = nodes.filter((node) => node.type === "Thesis").length;
  const focusType = payload.stats?.focus_type || "Thesis";
  const edges = (payload.edges || [])
    .map((edge) => ({
      ...edge,
      sourceNode: nodeById.get(edge.source),
      targetNode: nodeById.get(edge.target),
    }))
    .filter((edge) => edge.sourceNode && edge.targetNode);

  if (state.graphAnimationFrame) {
    cancelAnimationFrame(state.graphAnimationFrame);
    state.graphAnimationFrame = null;
  }

  if (!nodes.length) {
    svg.innerHTML = "";
    renderGraphLegend(payload);
    renderGraphInspector(null);
    applyGraphZoomTransform();
    return;
  }

  placeGraphNodes(nodes, width, height, focusType);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <g class="graph-viewport">
      <g class="graph-edge-layer">
        ${edges.map((edge, index) => `
          <line
          class="graph-edge ${edge.type === "ANALYSIS_LINK" ? "analysis-edge" : ""} ${edge.type === "DIRECT_RELATION" ? "direct-edge" : ""}"
          data-index="${index}"
          data-source="${escapeHtml(edge.source)}"
          data-target="${escapeHtml(edge.target)}"
          ></line>
        `).join("")}
      </g>
      <g class="graph-node-layer">
        ${nodes.map((node) => `
          <g class="graph-node type-${escapeHtml(node.type.toLowerCase())} ${graphNodeShouldShowLabel(node, visibleThesisCount, focusType) ? "labelled" : ""}" data-node-id="${escapeHtml(node.id)}" tabindex="0" role="button" aria-label="${escapeHtml(`${graphTypeLabel(node.type)}: ${node.label}`)}">
            <title>${escapeHtml(`${graphTypeLabel(node.type)}: ${node.label}`)}</title>
            <circle r="${node.radius}" fill="${escapeHtml(graphTypeColor(node.type))}"></circle>
            <text class="graph-node-label" y="${node.radius + 13}">${escapeHtml(graphVisibleLabel(node))}</text>
          </g>
        `).join("")}
      </g>
    </g>
  `;
  applyGraphZoomTransform();

  svg.querySelectorAll(".graph-node").forEach((element) => {
    const node = nodeById.get(element.dataset.nodeId);
    element.addEventListener("click", () => selectGraphNode(node.id));
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectGraphNode(node.id);
      }
    });
    bindGraphDrag(svg, element, node, nodes, edges);
  });

  renderGraphLegend(payload);
  renderGraphInspector(null);
  runGraphLayout(nodes, edges, width, height, focusType);
}

function placeGraphNodes(nodes, width, height, focusType = "Thesis") {
  const groups = new Map();
  nodes.forEach((node) => {
    if (!groups.has(node.type)) groups.set(node.type, []);
    groups.get(node.type).push(node);
  });
  const anchors = graphAnchorFractions(focusType);

  groups.forEach((items, type) => {
    const [anchorX, anchorY] = anchors[type] || [0.5, 0.5];
    const baseX = width * anchorX;
    const baseY = height * anchorY;
    const ring = type === "Thesis" ? Math.min(width, height) * 0.24 : Math.min(width, height) * 0.11;
    items.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, items.length);
      const radius = ring * (0.55 + (index % 4) * 0.16);
      node.x = clamp(baseX + Math.cos(angle) * radius, 28, width - 28);
      node.y = clamp(baseY + Math.sin(angle) * radius, 28, height - 28);
    });
  });
}

function runGraphLayout(nodes, edges, width, height, focusType = "Thesis") {
  let tick = 0;
  const maxTicks = 150;
  const anchors = Object.fromEntries(
    Object.entries(graphAnchorFractions(focusType)).map(([type, [x, y]]) => [type, [width * x, height * y]]),
  );

  function step() {
    applyGraphForces(nodes, edges, anchors, width, height);
    renderGraphPositions(nodes, edges);
    tick += 1;
    if (tick < maxTicks) {
      state.graphAnimationFrame = requestAnimationFrame(step);
    } else {
      state.graphAnimationFrame = null;
    }
  }

  renderGraphPositions(nodes, edges);
  state.graphAnimationFrame = requestAnimationFrame(step);
}

function graphAnchorFractions(focusType = "Thesis") {
  const anchors = {
    Thesis: [0.5, 0.52],
    Concept: [0.22, 0.24],
    Keyword: [0.22, 0.76],
    UseCase: [0.8, 0.28],
    Methodology: [0.78, 0.76],
    Year: [0.5, 0.13],
    MasterLevel: [0.1, 0.52],
    Track: [0.9, 0.52],
  };
  if (focusType && focusType !== "Thesis") {
    anchors[focusType] = [0.5, 0.52];
  }
  return anchors;
}

function applyGraphForces(nodes, edges, anchors, width, height) {
  edges.forEach((edge) => {
    const source = edge.sourceNode;
    const target = edge.targetNode;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const distance = Math.sqrt(dx * dx + dy * dy) || 1;
    const desired = source.type === "Thesis" && target.type === "Thesis" ? 130 : 95;
    const force = (distance - desired) * 0.0045;
    const fx = (dx / distance) * force;
    const fy = (dy / distance) * force;
    source.vx += fx;
    source.vy += fy;
    target.vx -= fx;
    target.vy -= fy;
  });

  for (let left = 0; left < nodes.length; left += 1) {
    for (let right = left + 1; right < nodes.length; right += 1) {
      const a = nodes[left];
      const b = nodes[right];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distanceSquared = Math.max(80, dx * dx + dy * dy);
      const distance = Math.sqrt(distanceSquared);
      const force = Math.min(2.2, 460 / distanceSquared);
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
  }

  nodes.forEach((node) => {
    const [anchorX, anchorY] = anchors[node.type] || [width * 0.5, height * 0.5];
    node.vx += (anchorX - node.x) * 0.002;
    node.vy += (anchorY - node.y) * 0.002;
    node.vx *= 0.82;
    node.vy *= 0.82;
    node.x = clamp(node.x + node.vx, node.radius + 18, width - node.radius - 18);
    node.y = clamp(node.y + node.vy, node.radius + 18, height - node.radius - 26);
  });
}

function renderGraphPositions(nodes, edges) {
  const svg = qs("#knowledge-graph-svg");
  edges.forEach((edge, index) => {
    const line = svg.querySelector(`.graph-edge[data-index="${index}"]`);
    if (!line) return;
    line.setAttribute("x1", edge.sourceNode.x);
    line.setAttribute("y1", edge.sourceNode.y);
    line.setAttribute("x2", edge.targetNode.x);
    line.setAttribute("y2", edge.targetNode.y);
  });
  nodes.forEach((node) => {
    const element = svg.querySelector(`.graph-node[data-node-id="${cssEscape(node.id)}"]`);
    if (element) {
      element.setAttribute("transform", `translate(${node.x.toFixed(2)} ${node.y.toFixed(2)})`);
    }
  });
}

function bindGraphDrag(svg, element, node, nodes, edges) {
  let dragging = false;
  element.addEventListener("pointerdown", (event) => {
    dragging = true;
    element.setPointerCapture(event.pointerId);
    if (state.graphAnimationFrame) {
      cancelAnimationFrame(state.graphAnimationFrame);
      state.graphAnimationFrame = null;
    }
    event.preventDefault();
  });
  element.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const point = graphPoint(svg, event.clientX, event.clientY);
    node.x = point.x;
    node.y = point.y;
    node.vx = 0;
    node.vy = 0;
    renderGraphPositions(nodes, edges);
  });
  element.addEventListener("pointerup", (event) => {
    dragging = false;
    element.releasePointerCapture(event.pointerId);
  });
  element.addEventListener("pointercancel", () => {
    dragging = false;
  });
}

function bindGraphViewportInteractions(svg) {
  svg.addEventListener("wheel", (event) => {
    if (!state.graphMap) return;
    event.preventDefault();
    const anchor = svgPoint(svg, event.clientX, event.clientY);
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    setGraphZoom(state.graphZoom.scale * factor, anchor);
  }, { passive: false });

  let panning = false;
  let previousPoint = null;

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest(".graph-node")) return;
    panning = true;
    previousPoint = svgPoint(svg, event.clientX, event.clientY);
    svg.classList.add("graph-panning");
    svg.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  svg.addEventListener("pointermove", (event) => {
    if (!panning || !previousPoint) return;
    const currentPoint = svgPoint(svg, event.clientX, event.clientY);
    state.graphZoom = {
      ...state.graphZoom,
      x: state.graphZoom.x + currentPoint.x - previousPoint.x,
      y: state.graphZoom.y + currentPoint.y - previousPoint.y,
    };
    previousPoint = currentPoint;
    applyGraphZoomTransform();
  });

  function stopPanning(event) {
    if (!panning) return;
    panning = false;
    previousPoint = null;
    svg.classList.remove("graph-panning");
    if (event.pointerId !== undefined && svg.hasPointerCapture(event.pointerId)) {
      svg.releasePointerCapture(event.pointerId);
    }
  }

  svg.addEventListener("pointerup", stopPanning);
  svg.addEventListener("pointercancel", stopPanning);
  svg.addEventListener("pointerleave", stopPanning);
}

function zoomGraphBy(factor) {
  const svg = qs("#knowledge-graph-svg");
  const rect = svg.getBoundingClientRect();
  const anchor = svgPoint(svg, rect.left + rect.width / 2, rect.top + rect.height / 2);
  setGraphZoom(state.graphZoom.scale * factor, anchor);
}

function resetGraphZoom() {
  state.graphZoom = { scale: 1, x: 0, y: 0 };
  applyGraphZoomTransform();
}

function setGraphZoom(nextScale, anchor) {
  const current = state.graphZoom;
  const scale = clamp(nextScale, GRAPH_ZOOM_MIN, GRAPH_ZOOM_MAX);
  if (!anchor) {
    state.graphZoom = { ...current, scale };
    applyGraphZoomTransform();
    return;
  }
  const graphAnchor = {
    x: (anchor.x - current.x) / current.scale,
    y: (anchor.y - current.y) / current.scale,
  };
  state.graphZoom = {
    scale,
    x: anchor.x - graphAnchor.x * scale,
    y: anchor.y - graphAnchor.y * scale,
  };
  applyGraphZoomTransform();
}

function applyGraphZoomTransform() {
  const zoom = state.graphZoom;
  const viewport = qs("#knowledge-graph-svg .graph-viewport");
  if (viewport) {
    viewport.setAttribute("transform", `translate(${zoom.x.toFixed(2)} ${zoom.y.toFixed(2)}) scale(${zoom.scale.toFixed(3)})`);
  }
  const label = qs("#graph-zoom-label");
  if (label) {
    label.textContent = `${Math.round(zoom.scale * 100)}%`;
  }
}

function graphPoint(svg, clientX, clientY) {
  const point = svgPoint(svg, clientX, clientY);
  const zoom = state.graphZoom;
  return {
    x: (point.x - zoom.x) / zoom.scale,
    y: (point.y - zoom.y) / zoom.scale,
  };
}

function svgPoint(svg, clientX, clientY) {
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}

function renderGraphLegend(payload) {
  const counts = payload.stats?.visible_node_counts || {};
  const types = Object.keys(graphTypeLabels).filter((type) => counts[type]);
  qs("#graph-legend").innerHTML = types
    .map((type) => `
      <span class="graph-legend-item">
        <span class="graph-legend-swatch" style="background:${escapeHtml(graphTypeColor(type))}"></span>
        ${escapeHtml(graphTypeLabel(type))} <strong>${formatNumber(counts[type])}</strong>
      </span>
    `)
    .join("");
}

function selectGraphNode(nodeId) {
  state.selectedGraphNodeId = nodeId;
  if (state.graphFilters.selectedOnly) {
    renderFilteredGraphMap();
    return;
  }
  renderGraphSelection();
  renderGraphInspector(nodeId);
}

function renderGraphSelection() {
  const payload = state.graphMap;
  if (!payload) return;
  const selected = state.selectedGraphNodeId;
  const connected = new Set([selected]);
  (payload.edges || []).forEach((edge) => {
    if (edge.source === selected) connected.add(edge.target);
    if (edge.target === selected) connected.add(edge.source);
  });
  qsa(".graph-node").forEach((element) => {
    const isConnected = connected.has(element.dataset.nodeId);
    element.classList.toggle("selected", element.dataset.nodeId === selected);
    element.classList.toggle("dimmed", Boolean(selected) && !isConnected);
  });
  qsa(".graph-edge").forEach((element) => {
    const isConnected = element.dataset.source === selected || element.dataset.target === selected;
    element.classList.toggle("selected", isConnected);
    element.classList.toggle("dimmed", Boolean(selected) && !isConnected);
  });
}

function renderGraphInspector(nodeId) {
  const container = qs("#graph-inspector");
  const payload = state.graphMap;
  if (!payload || !nodeId) {
    container.innerHTML = `<h3>Graph Inspector</h3><div class="empty-state">Select a node to inspect its metadata and direct connections.</div>`;
    return;
  }
  const node = (payload.nodes || []).find((item) => item.id === nodeId);
  if (!node) return;
  const nodeById = new Map((payload.nodes || []).map((item) => [item.id, item]));
  const directEdges = (payload.edges || []).filter((edge) => edge.source === nodeId || edge.target === nodeId);
  const neighbours = directEdges
    .map((edge) => {
      const neighbourId = edge.source === nodeId ? edge.target : edge.source;
      return { edge, node: nodeById.get(neighbourId) };
    })
    .filter((item) => item.node)
    .slice(0, 18);

  container.innerHTML = `
    <h3>${escapeHtml(graphTypeLabel(node.type))}</h3>
    <div class="graph-inspector-title">
      <span class="graph-type-pill" style="background:${escapeHtml(graphTypeColor(node.type))}">${escapeHtml(graphTypeLabel(node.type))}</span>
      <strong>${escapeHtml(node.label)}</strong>
      <span>${escapeHtml(node.subtitle || "")}</span>
    </div>
    ${node.type === "Thesis" ? renderGraphThesisActions(node) : ""}
    <div class="detail-section">
      <h4>Connections</h4>
      <div class="mini-list">
        ${neighbours.map(({ edge, node: neighbour }) => `
          <button class="mini-row graph-neighbour" type="button" data-node-id="${escapeHtml(neighbour.id)}">
            <strong>${escapeHtml(graphTypeLabel(neighbour.type))} | ${escapeHtml(truncate(neighbour.label, 76))}</strong>
            <span>${escapeHtml(formatGraphEdgeSummary(edge))}</span>
          </button>
        `).join("") || '<div class="muted">No visible direct connection.</div>'}
      </div>
    </div>
  `;
  qsa(".graph-neighbour").forEach((button) => {
    button.addEventListener("click", () => selectGraphNode(button.dataset.nodeId));
  });
  qsa(".graph-profile-button").forEach((button) => {
    button.addEventListener("click", () => openThesisProfile(button.dataset.thesisId));
  });
}

function renderGraphThesisActions(node) {
  const thesisId = node.metadata?.thesis_id || node.id.replace("thesis:", "");
  return `
    <div class="graph-inspector-actions">
      <button class="secondary-button compact-button graph-profile-button" type="button" data-thesis-id="${escapeHtml(thesisId)}">View profile</button>
      <a class="pdf-link compact-link" href="/api/files/${encodeURIComponent(thesisId)}" target="_blank" rel="noreferrer">Open PDF</a>
    </div>
  `;
}

function graphNodeRadius(node) {
  const base = node.type === "Thesis" ? 7 : 10;
  return Math.min(node.type === "Thesis" ? 13 : 20, base + Math.sqrt(Math.max(1, node.weight || 1)) * 1.6);
}

function graphVisibleLabel(node) {
  if (node.type === "Thesis") return truncate(node.label, 42);
  return truncate(node.label, 28);
}

function graphNodeShouldShowLabel(node, visibleThesisCount = Infinity, focusType = "Thesis") {
  const incoming = Number(node.incoming_edges || node.weight || 1);
  if (node.type === "Thesis") return visibleThesisCount <= GRAPH_TITLE_LABEL_THRESHOLD;
  if (visibleThesisCount === 0) return node.type === focusType || incoming >= 2;
  if (node.type === "Keyword") return false;
  if (node.type === "Concept") return incoming >= 12;
  return true;
}

function graphTypeColor(type) {
  return graphTypeColors[type] || "#627083";
}

function graphTypeLabel(type) {
  return graphTypeLabels[type] || type;
}

function formatGraphEdgeType(type) {
  return String(type || "").toLowerCase().replaceAll("_", " ");
}

function formatGraphEdgeSummary(edge) {
  if (edge.type === "ANALYSIS_LINK") {
    const count = Number(edge.weight || 0);
    return `shared by ${formatNumber(count)} ${count === 1 ? "thesis" : "theses"}`;
  }
  if (edge.type === "DIRECT_RELATION") {
    const count = Number(edge.weight || 0);
    return `direct relation through ${formatNumber(count)} ${count === 1 ? "thesis" : "theses"}`;
  }
  return formatGraphEdgeType(edge.type);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(value);
  }
  return String(value).replaceAll('"', '\\"').replaceAll("\\", "\\\\");
}

async function loadFacets() {
  state.facets = await api.get("/api/facets");
  fillSelect(qs("#concept-filter"), state.facets.concepts || [], "All concepts");
  fillSelect(qs("#year-filter"), state.facets.years || [], "All years");
  fillSelect(qs("#level-filter"), state.facets.master_levels || [], "All levels");
  fillSelect(qs("#track-filter"), state.facets.tracks || [], "All tracks");
  fillGraphFilterSelects();
}

function fillGraphFilterSelects() {
  if (!state.facets) return;
  fillSelect(qs("#graph-concept-filter"), graphFilterItems("Concept", state.facets.concepts || []), "All concepts", state.graphFilters.concept);
  fillSelect(qs("#graph-use-case-filter"), graphFilterItems("UseCase", state.facets.use_cases || []), "All use cases", state.graphFilters.useCase);
  fillSelect(qs("#graph-year-filter"), graphFilterItems("Year", state.facets.years || []), "All years", state.graphFilters.year);
  fillSelect(qs("#graph-level-filter"), graphFilterItems("MasterLevel", state.facets.master_levels || []), "All levels", state.graphFilters.masterLevel);
  fillSelect(qs("#graph-track-filter"), graphFilterItems("Track", state.facets.tracks || []), "All tracks", state.graphFilters.track);
  state.graphFilters = {
    ...state.graphFilters,
    concept: valueOf("#graph-concept-filter"),
    useCase: valueOf("#graph-use-case-filter"),
    year: valueOf("#graph-year-filter"),
    masterLevel: valueOf("#graph-level-filter"),
    track: valueOf("#graph-track-filter"),
  };
}

function graphFilterItems(nodeType, fallbackItems) {
  const graphNodes = state.graphMapRaw?.nodes || [];
  if (!graphNodes.length) return fallbackItems;
  const labels = [...new Set(graphNodes.filter((node) => node.type === nodeType).map((node) => node.label).filter(Boolean))];
  labels.sort((left, right) => String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" }));
  return labels.map((label) => ({ label }));
}

function fillSelect(select, items, defaultLabel, selectedValue = "") {
  select.innerHTML = `<option value="">${escapeHtml(defaultLabel)}</option>${items
    .map((item) => {
      const label = typeof item === "object" && item !== null ? item.label : item;
      return `<option value="${escapeHtml(label)}">${escapeHtml(label)}</option>`;
    })
    .join("")}`;
  if (selectedValue && [...select.options].some((option) => option.value === selectedValue)) {
    select.value = selectedValue;
  }
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
  const useLlm = qs("#rag-use-llm").checked;
  const showAll = qs("#rag-show-all").checked;
  const topK = showAll ? 5 : normalizedRagTopK();
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
          top_k: 5,
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
        `Retrieved ${formatNumber(sources.count || 0)} of ${formatNumber(sources.total || 0)} relevant source theses${domainFilterSuffix(sources)}.`,
        answer.answer_mode === "ollama_unavailable" ? "warning" : "success",
      );
    } else {
      const result = await api.postJson("/api/rag/answer", {
        question,
        top_k: topK,
        use_llm: useLlm,
      });
      renderRagResult(result);
      renderRagStatus(`Retrieved ${formatNumber(result.results?.length || 0)} relevant source theses${domainFilterSuffix(result)}.`, result.answer_mode === "ollama_unavailable" ? "warning" : "success");
    }
  } catch (error) {
    renderRagStatus(error.message, "error");
  } finally {
    setRagBusy(false);
  }
}

function domainFilterSuffix(result) {
  const domains = result.domain_filters || [];
  return domains.length ? ` with ${domains.join(", ")} domain filtering` : "";
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
    renderRagStatus(`Showing ${formatNumber(result.count || 0)} of ${formatNumber(result.total || 0)} relevant source theses.`, "success");
  } catch (error) {
    renderRagStatus(error.message, "error");
  } finally {
    setRagBusy(false);
  }
}

function renderRagResult(result, sourcePage = null) {
  const minScore = result.min_score ?? sourcePage?.min_score;
  qs("#rag-meta").textContent = `${result.embedding_model || "local"} | ${result.embedding_dimensions || 0} dimensions${minScore !== undefined ? ` | min score ${formatScore(minScore)}` : ""}`;
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
        <span class="rag-score" title="Relevance score">${formatScore(row.score)}</span>
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
  qs("#rag-top-k").classList.toggle("hidden", showAll);
  qs("#rag-page-size-display").classList.toggle("hidden", !showAll);
  qs("#rag-top-k-label-text").textContent = showAll ? "Source pages" : "Max results";
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
    qs("#file-label").textContent = "Select one or more PDF files";
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
      renderImportStatus(`Approved ${result.thesis_id}. Next draft selected. Neo4j, CSV, graph, and RAG are updated.`, "success");
    } else {
      renderImportStatus(`Approved ${result.thesis_id}. Neo4j, CSV, graph, and RAG are updated.`, "success");
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

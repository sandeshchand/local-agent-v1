const API_TOKEN_STORAGE_KEY = "local-agent-api-token";
const SESSION_STORAGE_KEY = "local-agent-session-id";

function setChatStatus(text) {
  const statusEl = document.getElementById("chat-status");
  if (statusEl) {
    statusEl.textContent = text;
  }
}

function setSendButtonLoading(isLoading) {
  const sendBtn = document.getElementById("send-btn");
  const chatInput = document.getElementById("chat-input");

  if (sendBtn) {
    sendBtn.disabled = isLoading;
    sendBtn.textContent = isLoading ? "Thinking..." : "Send";
  }

  if (chatInput) {
    chatInput.disabled = isLoading;
  }

  setChatStatus(isLoading ? "Generating response..." : "Ready");
}

function setIngestLoading(isLoading) {
  const ingestBtn = document.getElementById("ingest-btn");
  const ingestInput = document.getElementById("ingest-path");
  const ingestForce = document.getElementById("ingest-force");

  if (ingestBtn) {
    ingestBtn.disabled = isLoading;
    ingestBtn.textContent = isLoading ? "Ingesting..." : "Ingest";
  }

  if (ingestInput) {
    ingestInput.disabled = isLoading;
  }
  if (ingestForce) {
    ingestForce.disabled = isLoading;
  }
}

async function fetchJSON(url, options = {}) {
  const token = getStoredApiToken();
  const sessionId = getStoredSessionId();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (sessionId) {
    headers["X-Local-Agent-Session"] = sessionId;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && data.detail
        ? data.detail
        : String(data);
    throw new Error(detail);
  }

  return data;
}

function getStoredApiToken() {
  return window.localStorage.getItem(API_TOKEN_STORAGE_KEY) || "";
}

function getStoredSessionId() {
  return window.localStorage.getItem(SESSION_STORAGE_KEY) || "default";
}

function saveAccessSettings() {
  const tokenInput = document.getElementById("api-token");
  const sessionInput = document.getElementById("ui-session-id");
  const memorySessionInput = document.getElementById("memory-session-id");
  const status = document.getElementById("access-status");
  const token = tokenInput ? tokenInput.value.trim() : "";
  const sessionId = sessionInput ? sessionInput.value.trim() || "default" : "default";

  if (token) {
    window.localStorage.setItem(API_TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(API_TOKEN_STORAGE_KEY);
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);

  if (memorySessionInput) {
    memorySessionInput.value = sessionId;
  }
  if (status) {
    status.textContent = token
      ? `Saved token and session ${sessionId}.`
      : `Saved session ${sessionId}. Token cleared.`;
    status.className = "status-box";
  }

  loadDocuments();
  loadTools();
  loadToolAudit();
  loadMemory();
  loadSystemStatus();
  loadIngestionStatus();
  loadRecentTraces();
  loadFeedbackSummary();
  loadFeedbackItems();
  loadEvalCandidates();
}

function loadAccessSettings() {
  const tokenInput = document.getElementById("api-token");
  const sessionInput = document.getElementById("ui-session-id");
  const memorySessionInput = document.getElementById("memory-session-id");
  const status = document.getElementById("access-status");
  const token = getStoredApiToken();
  const sessionId = getStoredSessionId();

  if (tokenInput) {
    tokenInput.value = token;
  }
  if (sessionInput) {
    sessionInput.value = sessionId;
  }
  if (memorySessionInput) {
    memorySessionInput.value = sessionId;
  }
  if (status) {
    status.textContent = token
      ? `Using saved token for session ${sessionId}.`
      : `Local mode. Session ${sessionId}.`;
    status.className = "status-box muted";
  }
}

function hideEmptyState() {
  const emptyState = document.getElementById("empty-state");
  if (emptyState) {
    emptyState.style.display = "none";
  }
}

function createElement(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  if (text) {
    element.textContent = text;
  }
  return element;
}

function shortText(value, maxLength = 160) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3)}...`;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const TRACE_PATH_LABELS = {
  deterministic_fast_path: "Deterministic fast path",
  extractive_fast_path: "Extractive fast path",
  llm_judge: "LLM judge",
  llm_generation: "LLM generation",
  heuristic_fallback_after_llm: "Heuristic fallback",
  generic_extractive_fallback: "Extractive fallback",
  source_window_extractive_replacement: "Source-window replacement",
  definition_extractive_replacement: "Definition replacement",
  pipeline_extractive_replacement: "Pipeline replacement",
  no_answer_context: "No answer context",
  not_selected: "Not selected",
};

function humanizePath(value) {
  const key = String(value || "").trim();
  if (!key) return "-";
  return TRACE_PATH_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function pathTone(value) {
  const key = String(value || "").toLowerCase();
  if (!key) return "";
  if (key.includes("fast_path") || key.includes("verified")) return "ok";
  if (key.includes("llm") || key.includes("replacement") || key.includes("fallback")) return "warn";
  if (key.includes("no_") || key.includes("error") || key.includes("deny")) return "bad";
  return "";
}

function compactReason(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace(/_/g, " ");
}

function latestStepOfType(trace, type) {
  const steps = Array.isArray(trace.steps) ? trace.steps : [];
  return [...steps].reverse().find((step) => step.type === type) || null;
}

function answerFastPath(step) {
  const answerTrace = step && step.answer_trace ? step.answer_trace : {};
  return answerTrace.fast_path || {};
}

function rejectionSummary(rejections) {
  if (!Array.isArray(rejections) || !rejections.length) return "";
  const counts = {};
  rejections.forEach((item) => {
    const reason = compactReason(item && item.reason ? item.reason : "rejected");
    counts[reason] = (counts[reason] || 0) + 1;
  });
  return Object.entries(counts)
    .map(([reason, count]) => `${reason}${count > 1 ? ` x${count}` : ""}`)
    .join(", ");
}

function formatPercent(value) {
  const number = Number(value || 0);
  return `${Math.round(number * 100)}%`;
}

const FEEDBACK_ISSUES = [
  ["", "Tag issue"],
  ["wrong_document", "Wrong doc"],
  ["bad_retrieval", "Bad retrieval"],
  ["weak_answer", "Weak answer"],
  ["missing_citation", "Missing citation"],
  ["tool_issue", "Tool issue"],
  ["other", "Other"],
];

function feedbackIssueLabel(issueType) {
  const match = FEEDBACK_ISSUES.find(([value]) => value === issueType);
  return match ? match[1] : "Tag issue";
}

function requirementsToText(items) {
  if (!Array.isArray(items)) return "";
  return items
    .map((item) => Array.isArray(item) ? item.join(" | ") : String(item || ""))
    .filter(Boolean)
    .join("\n");
}

function textToRequirements(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (!line.includes("|")) return line;
      return line
        .split("|")
        .map((part) => part.trim())
        .filter(Boolean);
    });
}

let currentFeedbackFilter = "all";
let currentTools = [];
let currentToolFilter = "";
let documentQuery = "";
let documentOffset = 0;
const DOCUMENT_PAGE_SIZE = 12;

function createIcon(paths) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");

  paths.forEach((pathData) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathData);
    svg.appendChild(path);
  });

  return svg;
}

function createThumbIcon(rating) {
  if (rating === "dislike") {
    return createIcon([
      "M17 14V2",
      "M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z",
    ]);
  }

  return createIcon([
    "M7 10v12",
    "M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z",
  ]);
}

function sourceFileName(path) {
  const text = String(path || "").trim();
  if (!text) return "Unknown file";
  const parts = text.split(/[\\/]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : text;
}

function renderSourcesBox(citations) {
  const box = createElement("details", "sources-box");
  box.open = citations.length <= 1;

  const header = createElement("summary", "sources-header");
  header.appendChild(createElement("strong", "", "Sources"));
  header.appendChild(createElement("span", "", `${citations.length} cited chunk${citations.length === 1 ? "" : "s"}`));
  box.appendChild(header);

  const list = createElement("ol", "sources-list");
  citations.forEach((citation) => {
    const item = createElement("li", "source-row");
    const title = createElement(
      "div",
      "source-main",
      `[${citation.index}] ${shortText(citation.title, 110)} - page ${formatValue(citation.page_number)}`
    );
    const file = createElement("div", "source-meta", sourceFileName(citation.source_path));
    file.title = citation.source_path || "";

    item.appendChild(title);
    item.appendChild(file);
    list.appendChild(item);
  });

  box.appendChild(list);
  return box;
}

function setWorkspaceTab(tabName) {
  const selected = tabName || "trace";

  document.querySelectorAll(".workspace-tab").forEach((button) => {
    const isActive = button.dataset.workspaceTab === selected;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  document.querySelectorAll(".workspace-tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.workspacePanel === selected);
  });
}

function setFeedbackState(container, selectedRating, statusText) {
  const buttons = container.querySelectorAll(".feedback-btn");
  buttons.forEach((button) => {
    const isSelected = button.dataset.rating === selectedRating;
    button.disabled = false;
    button.classList.toggle("selected", isSelected);
  });

  const status = container.querySelector(".feedback-status");
  if (status) {
    status.textContent = statusText;
  }
}

async function submitFeedback(traceId, rating, container) {
  if (!traceId || !container) return;

  const buttons = container.querySelectorAll(".feedback-btn");
  const status = container.querySelector(".feedback-status");
  buttons.forEach((button) => {
    button.disabled = true;
  });
  if (status) {
    status.textContent = "Saving...";
  }

  try {
    await fetchJSON("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ trace_id: traceId, rating }),
    });
    setFeedbackState(container, rating, "Saved");
    loadFeedbackSummary();
    loadFeedbackItems();
  } catch (error) {
    buttons.forEach((button) => {
      button.disabled = false;
    });
    if (status) {
      status.textContent = `Could not save: ${error.message}`;
    }
  }
}

function renderFeedbackControls(traceId) {
  const container = createElement("div", "feedback-row");
  container.appendChild(createElement("span", "feedback-label", "Was this answer useful?"));

  const likeButton = createElement("button", "feedback-btn");
  likeButton.type = "button";
  likeButton.dataset.rating = "like";
  likeButton.setAttribute("aria-label", "Like this answer");
  likeButton.title = "Like this answer";
  likeButton.appendChild(createThumbIcon("like"));

  const dislikeButton = createElement("button", "feedback-btn");
  dislikeButton.type = "button";
  dislikeButton.dataset.rating = "dislike";
  dislikeButton.setAttribute("aria-label", "Dislike this answer");
  dislikeButton.title = "Dislike this answer";
  dislikeButton.appendChild(createThumbIcon("dislike"));

  const status = createElement("span", "feedback-status", "");

  likeButton.addEventListener("click", () => submitFeedback(traceId, "like", container));
  dislikeButton.addEventListener("click", () => submitFeedback(traceId, "dislike", container));

  container.appendChild(likeButton);
  container.appendChild(dislikeButton);
  container.appendChild(status);
  return container;
}

function addMessage(role, content, extraClass = "") {
  hideEmptyState();

  const template = document.getElementById("message-template");
  const chatWindow = document.getElementById("chat-window");

  if (!template || !chatWindow) return;

  const clone = template.content.cloneNode(true);
  const roleEl = clone.querySelector(".message-role");
  const bodyEl = clone.querySelector(".message-body");
  const messageEl = clone.querySelector(".message");

  if (!roleEl || !bodyEl || !messageEl) return;

  roleEl.textContent = role;
  bodyEl.textContent = content;

  if (role.toLowerCase() === "user") {
    messageEl.classList.add("user");
  } else {
    messageEl.classList.add("assistant");
  }

  if (extraClass) {
    messageEl.classList.add(extraClass);
  }

  chatWindow.appendChild(clone);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addApprovalControls(container, query, approval) {
  if (!container || !approval || !approval.needsApproval || !approval.toolName) return;

  const panel = createElement("div", "approval-panel");
  panel.appendChild(createElement("strong", "", "Approval required"));
  panel.appendChild(createElement("span", "", approval.toolName));
  if (approval.reason) {
    panel.appendChild(createElement("p", "", approval.reason));
  }

  const actions = createElement("div", "approval-actions");
  const approveButton = createElement("button", "approval-btn", "Approve and run");
  approveButton.type = "button";
  approveButton.addEventListener("click", () => approveAndRun(query, approval.toolName, approveButton));
  actions.appendChild(approveButton);
  panel.appendChild(actions);
  container.appendChild(panel);
}

function addAssistantResponse(answer, traceId, citations = [], options = {}) {
  hideEmptyState();

  const chatWindow = document.getElementById("chat-window");
  if (!chatWindow) return;

  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";

  const role = document.createElement("div");
  role.className = "message-role";
  role.textContent = "Assistant";

  const body = document.createElement("div");
  body.className = "message-body";

  const answerBox = document.createElement("div");
  answerBox.className = "answer-box";
  answerBox.textContent = answer;

  body.appendChild(answerBox);

  addApprovalControls(body, options.query || "", options.approval || {});

  const answerActions = document.createElement("div");
  answerActions.className = "answer-actions";
  answerActions.appendChild(renderFeedbackControls(traceId));

  const traceRow = document.createElement("div");
  traceRow.className = "trace-action-row";

  const trace = document.createElement("button");
  trace.type = "button";
  trace.className = "trace-badge";
  trace.textContent = `Trace ${traceId}`;
  trace.addEventListener("click", () => loadTrace(traceId));
  traceRow.appendChild(trace);
  answerActions.appendChild(traceRow);
  body.appendChild(answerActions);

  if (Array.isArray(citations) && citations.length > 0) {
    body.appendChild(renderSourcesBox(citations));
  }

  wrapper.appendChild(role);
  wrapper.appendChild(body);
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  loadTrace(traceId);
  loadRecentTraces();
  loadToolAudit();
  loadMemory();
}

async function approveAndRun(query, toolName, button) {
  if (!query || !toolName || !button) return;

  button.disabled = true;
  button.textContent = "Running...";
  setSendButtonLoading(true);

  try {
    const data = await fetchJSON("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        query,
        approved_tools: [toolName],
      }),
    });
    button.textContent = "Approved";
    button.classList.add("done");
    addAssistantResponse(data.answer, data.trace_id, data.citations || [], {
      query,
      approval: {
        needsApproval: data.needs_approval,
        toolName: data.approval_tool_name,
        reason: data.approval_reason,
      },
    });
  } catch (error) {
    button.disabled = false;
    button.textContent = "Approve and run";
    addMessage("Assistant", `Approval failed: ${error.message}`, "error-message");
  } finally {
    setSendButtonLoading(false);
  }
}

function metric(label, value, tone = "") {
  const item = createElement("div", `trace-metric ${tone}`);
  item.appendChild(createElement("span", "trace-metric-label", label));
  item.appendChild(createElement("strong", "", formatValue(value)));
  return item;
}

function traceChip(text, tone = "") {
  return createElement("span", `trace-chip ${tone}`, text);
}

function renderTracePathSummary(trace) {
  const summary = createElement("div", "trace-path-grid");
  const retrieveStep = latestStepOfType(trace, "retrieve");
  if (!retrieveStep) {
    summary.appendChild(createElement("div", "muted", "No retrieval path metadata for this trace."));
    return summary;
  }

  const fastPath = answerFastPath(retrieveStep);
  const answerTrace = retrieveStep.answer_trace || {};
  const evidenceTrace = retrieveStep.evidence_trace || {};
  const cards = [
    ["Evidence path", humanizePath(retrieveStep.evidence_path), pathTone(retrieveStep.evidence_path)],
    ["Answer path", humanizePath(retrieveStep.answer_path), pathTone(retrieveStep.answer_path)],
    ["Evidence shape", humanizePath(evidenceTrace.fast_path_shape || evidenceTrace.path), pathTone(evidenceTrace.path)],
    [
      "Answer fast path",
      fastPath.used ? `Accepted ${humanizePath(fastPath.accepted_candidate_source)}` : compactReason(fastPath.reason || answerTrace.fallback_reason || "not used"),
      fastPath.used ? "ok" : "warn",
    ],
  ];

  cards.forEach(([label, value, tone]) => {
    const card = createElement("div", "trace-path-card");
    card.appendChild(createElement("span", "", label));
    card.appendChild(traceChip(value, tone));
    summary.appendChild(card);
  });

  const rejections = rejectionSummary(fastPath.rejections);
  if (rejections) {
    const card = createElement("div", "trace-path-card wide");
    card.appendChild(createElement("span", "", "Rejected candidates"));
    card.appendChild(createElement("strong", "", shortText(rejections, 180)));
    summary.appendChild(card);
  }

  return summary;
}

function setTraceStatus(text) {
  const empty = document.getElementById("trace-empty");
  const detail = document.getElementById("trace-detail");
  if (empty) {
    empty.textContent = text;
    empty.style.display = "block";
  }
  if (detail) {
    detail.classList.add("hidden");
  }
}

function renderKeyValues(container, values) {
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === false) {
      return;
    }
    const row = createElement("div", "trace-kv");
    row.appendChild(createElement("span", "", key));
    row.appendChild(createElement("strong", "", formatValue(value)));
    container.appendChild(row);
  });
}

function stepTitle(step) {
  const type = step.type || "step";
  if (type === "retrieve") return `Retrieval attempt ${step.attempt || 1}`;
  if (type === "guardrail") return `Guardrail: ${step.status || "checked"}`;
  if (type === "tool_call") return `Tool: ${step.tool_name || "unknown"}`;
  if (type === "verify") return `Verifier: ${step.status || "checked"}`;
  if (type === "answer_repair") return "Answer repair";
  if (type === "retrieval_retry_decision") return "Retry decision";
  return type.replace(/_/g, " ");
}

function stepTone(step) {
  const status = String(step.status || "").toLowerCase();
  if (status.includes("verified") || status === "allow") return "ok";
  if (status.includes("approval") || status === "needs_approval") return "warn";
  if (status.includes("deny") || status.includes("error")) return "bad";
  if (step.accepted === true || step.success === true) return "ok";
  if (step.accepted === false || step.success === false) return "warn";
  return "";
}

function renderStep(step) {
  const item = createElement("div", `trace-step ${stepTone(step)}`);
  const title = createElement("div", "trace-step-title");
  title.appendChild(createElement("span", "", stepTitle(step)));
  title.appendChild(createElement("em", "", step.step !== undefined ? `#${step.step}` : ""));
  item.appendChild(title);

  const details = createElement("div", "trace-step-details");
  if (step.type === "retrieve") {
    const pathRow = createElement("div", "trace-step-paths");
    pathRow.appendChild(traceChip(`Evidence: ${humanizePath(step.evidence_path)}`, pathTone(step.evidence_path)));
    pathRow.appendChild(traceChip(`Answer: ${humanizePath(step.answer_path)}`, pathTone(step.answer_path)));
    const fastPath = answerFastPath(step);
    if (fastPath.used && fastPath.accepted_candidate_source) {
      pathRow.appendChild(traceChip(`Accepted: ${humanizePath(fastPath.accepted_candidate_source)}`, "ok"));
    }
    const rejections = rejectionSummary(fastPath.rejections);
    if (rejections) {
      pathRow.appendChild(traceChip(`Rejected: ${shortText(rejections, 120)}`, "warn"));
    }
    details.appendChild(pathRow);
    renderKeyValues(details, {
      query: shortText(step.retrieval_query, 120),
      scope: step.candidate_scope,
      results: step.result_count,
      selected: step.selected_count,
      context: step.answer_context_count,
      retry: step.retry,
      reason: step.retry_reason,
    });
    const routed = Array.isArray(step.routed_docs) ? step.routed_docs.slice(0, 3) : [];
    if (routed.length) {
      const docs = createElement("div", "trace-mini-list");
      routed.forEach((doc) => {
        docs.appendChild(
          createElement(
            "div",
            "",
            `${shortText(doc.title, 86)} - score ${Number(doc.routing_score || 0).toFixed(2)}`
          )
        );
      });
      details.appendChild(docs);
    }
  } else if (step.type === "guardrail") {
    renderKeyValues(details, {
      tool: step.tool_name,
      status: step.status,
      approved: step.approved,
      approval_required: step.requires_approval,
      reason: step.reason,
    });
  } else if (step.type === "verify") {
    renderKeyValues(details, {
      status: step.status,
      grounded: step.grounded,
      issues: Array.isArray(step.issues) ? step.issues.join("; ") : "",
    });
  } else {
    renderKeyValues(details, step);
  }

  item.appendChild(details);
  return item;
}

function renderEvidenceItem(item, index) {
  const evidence = createElement("div", "evidence-item");
  evidence.appendChild(
    createElement(
      "div",
      "evidence-title",
      `[${index + 1}] ${shortText(item.title || "Untitled", 95)}`
    )
  );
  evidence.appendChild(
    createElement(
      "div",
      "evidence-meta",
      `Page ${formatValue(item.page_number || item.page_numbers)} - ${shortText(item.section_title, 80)}`
    )
  );
  evidence.appendChild(createElement("p", "", shortText(item.text, 260)));
  return evidence;
}

function renderTrace(trace) {
  const empty = document.getElementById("trace-empty");
  const detail = document.getElementById("trace-detail");
  const idLabel = document.getElementById("trace-id-label");
  const query = document.getElementById("trace-query");
  const statusPill = document.getElementById("trace-status-pill");
  const metrics = document.getElementById("trace-metrics");
  const pathSummary = document.getElementById("trace-path-summary");
  const steps = document.getElementById("trace-steps");
  const evidence = document.getElementById("trace-evidence");
  const tools = document.getElementById("trace-tools");
  const raw = document.getElementById("trace-raw-json");

  if (!detail || !empty || !metrics || !pathSummary || !steps || !evidence || !tools || !raw) return;

  empty.style.display = "none";
  detail.classList.remove("hidden");

  const verification = trace.verification || {};
  const plan = trace.plan || {};
  const retrievedItems = Array.isArray(trace.retrieved_items) ? trace.retrieved_items : [];
  const toolResults = Array.isArray(trace.tool_results) ? trace.tool_results : [];

  idLabel.textContent = `Trace ${trace.trace_id} - ${trace.created_at || ""}`;
  query.textContent = trace.query || "Untitled trace";
  statusPill.textContent = verification.status || "no verifier";
  statusPill.className = `trace-status-pill ${
    verification.status === "verified" ? "ok" : verification.status ? "warn" : ""
  }`;

  metrics.innerHTML = "";
  metrics.appendChild(metric("Mode", plan.mode || "unknown"));
  metrics.appendChild(metric("Top K", trace.top_k));
  metrics.appendChild(metric("Evidence", retrievedItems.length));
  metrics.appendChild(metric("Tools", toolResults.length));

  pathSummary.innerHTML = "";
  pathSummary.appendChild(renderTracePathSummary(trace));

  steps.innerHTML = "";
  const stepItems = Array.isArray(trace.steps) ? trace.steps : [];
  if (stepItems.length) {
    stepItems.forEach((step) => steps.appendChild(renderStep(step)));
  } else {
    steps.appendChild(createElement("div", "muted", "No trace steps recorded."));
  }

  evidence.innerHTML = "";
  if (retrievedItems.length) {
    retrievedItems.slice(0, 6).forEach((item, index) => evidence.appendChild(renderEvidenceItem(item, index)));
  } else {
    evidence.appendChild(createElement("div", "muted", "No retrieved evidence for this trace."));
  }

  tools.innerHTML = "";
  if (toolResults.length) {
    toolResults.forEach((tool) => {
      const item = createElement("div", "tool-result-item");
      renderKeyValues(item, {
        tool: tool.tool_name,
        success: tool.success,
        output: shortText(tool.output, 220),
        error: tool.error,
      });
      tools.appendChild(item);
    });
  } else {
    tools.appendChild(createElement("div", "muted", "No tool result for this trace."));
  }

  raw.textContent = JSON.stringify(trace, null, 2);
}

async function loadTrace(traceId) {
  if (!traceId) return;
  setWorkspaceTab("trace");
  setTraceStatus(`Loading trace ${traceId}...`);
  try {
    const trace = await fetchJSON(`/api/traces/${traceId}`);
    renderTrace(trace);
  } catch (error) {
    setTraceStatus(`Could not load trace: ${error.message}`);
  }
}

function renderRecentTraces(traces) {
  const container = document.getElementById("recent-traces");
  if (!container) return;
  container.innerHTML = "";

  if (!traces.length) {
    container.appendChild(createElement("div", "muted", "No traces yet."));
    return;
  }

  traces.forEach((trace) => {
    const item = createElement("button", "recent-trace-item");
    item.type = "button";
    item.appendChild(createElement("strong", "", `#${trace.trace_id} ${shortText(trace.query, 70)}`));
    item.appendChild(
      createElement(
        "span",
        "",
        `${trace.verification_status || "no verifier"} - ${trace.created_at || ""}`
      )
    );
    item.addEventListener("click", () => loadTrace(trace.trace_id));
    container.appendChild(item);
  });
}

async function loadRecentTraces() {
  try {
    const traces = await fetchJSON("/api/traces?limit=8");
    renderRecentTraces(traces);
  } catch (error) {
    const container = document.getElementById("recent-traces");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Trace error: ${error.message}`));
    }
  }
}

function setFeedbackFilter(filter) {
  currentFeedbackFilter = filter;
  document.querySelectorAll(".feedback-filter-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.feedbackFilter === filter);
  });
  loadFeedbackItems();
}

function renderFeedbackSummary(summary) {
  const container = document.getElementById("feedback-summary");
  if (!container) return;
  container.innerHTML = "";

  if (!summary) {
    container.appendChild(createElement("div", "muted", "No feedback summary yet."));
    return;
  }

  const metrics = [
    ["Total", summary.total_count],
    ["Liked", summary.like_count],
    ["Disliked", summary.dislike_count],
    ["Dislike Rate", formatPercent(summary.dislike_rate)],
  ];

  const grid = createElement("div", "feedback-summary-grid");
  metrics.forEach(([label, value]) => {
    const item = createElement("div", "feedback-summary-item");
    item.appendChild(createElement("span", "", label));
    item.appendChild(createElement("strong", "", formatValue(value)));
    grid.appendChild(item);
  });
  container.appendChild(grid);

  const recentDislikes = Array.isArray(summary.recent_dislikes)
    ? summary.recent_dislikes.length
    : 0;
  const cue = recentDislikes
    ? `${recentDislikes} recent disliked answer${recentDislikes === 1 ? "" : "s"} ready for review.`
    : "No disliked answers in the review queue.";
  container.appendChild(createElement("div", "feedback-summary-cue", cue));

  const issueCounts = summary.issue_counts || {};
  const issueEntries = Object.entries(issueCounts).filter(([, count]) => Number(count) > 0);
  if (issueEntries.length) {
    const issueRow = createElement("div", "feedback-issue-counts");
    issueEntries.forEach(([issueType, count]) => {
      issueRow.appendChild(
        createElement(
          "span",
          "feedback-issue-chip",
          `${feedbackIssueLabel(issueType)} ${count}`
        )
      );
    });
    container.appendChild(issueRow);
  }
}

async function loadFeedbackSummary() {
  try {
    const summary = await fetchJSON("/api/feedback/summary");
    renderFeedbackSummary(summary);
  } catch (error) {
    const container = document.getElementById("feedback-summary");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Feedback summary error: ${error.message}`));
    }
  }
}

function renderFeedbackItems(items) {
  const container = document.getElementById("feedback-review-list");
  if (!container) return;
  container.innerHTML = "";

  if (!Array.isArray(items) || !items.length) {
    container.appendChild(createElement("div", "muted", "No feedback yet."));
    return;
  }

  items.forEach((record) => {
    const item = createElement("article", `feedback-review-item ${record.rating || ""}`);

    const top = createElement("div", "feedback-review-top");
    top.appendChild(createElement("span", `feedback-rating-pill ${record.rating || ""}`, record.rating || "unknown"));
    top.appendChild(createElement("span", "feedback-review-time", record.updated_at || ""));

    item.appendChild(top);
    item.appendChild(
      createElement(
        "strong",
        "",
        `#${record.trace_id} ${shortText(record.query, 72)}`
      )
    );
    item.appendChild(createElement("span", "", shortText(record.final_answer, 115)));

    const actions = createElement("div", "feedback-review-actions");
    const openButton = createElement("button", "feedback-action-btn", "Open trace");
    openButton.type = "button";
    openButton.addEventListener("click", () => loadTrace(record.trace_id));
    actions.appendChild(openButton);

    if (record.rating === "dislike") {
      const issueSelect = createElement("select", "feedback-issue-select");
      issueSelect.setAttribute("aria-label", "Feedback issue type");
      FEEDBACK_ISSUES.forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        issueSelect.appendChild(option);
      });
      issueSelect.value = record.issue_type || "";
      issueSelect.addEventListener("change", () => saveFeedbackIssue(record, issueSelect));
      actions.appendChild(issueSelect);

      const evalButton = createElement("button", "feedback-action-btn", "Create eval");
      evalButton.type = "button";
      evalButton.addEventListener("click", () => createEvalCandidate(record.trace_id, evalButton));
      actions.appendChild(evalButton);
    }

    item.appendChild(actions);
    container.appendChild(item);
  });
}

async function loadFeedbackItems() {
  const query = currentFeedbackFilter === "all" ? "" : `&rating=${currentFeedbackFilter}`;
  try {
    const items = await fetchJSON(`/api/feedback?limit=10${query}`);
    renderFeedbackItems(items);
  } catch (error) {
    const container = document.getElementById("feedback-review-list");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Feedback error: ${error.message}`));
    }
  }
}

async function saveFeedbackIssue(record, select) {
  if (!record || !select) return;
  select.disabled = true;
  try {
    const updated = await fetchJSON("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        trace_id: record.trace_id,
        rating: record.rating,
        issue_type: select.value,
      }),
    });
    record.issue_type = updated.issue_type || "";
    select.title = "Saved";
    loadFeedbackSummary();
  } catch (error) {
    select.title = error.message;
  } finally {
    select.disabled = false;
  }
}

async function createEvalCandidate(traceId, button) {
  if (!traceId || !button) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Creating...";
  button.classList.remove("done");

  try {
    const result = await fetchJSON("/api/eval-candidates", {
      method: "POST",
      body: JSON.stringify({ trace_id: traceId }),
    });
    button.textContent = result.status === "created" ? "Eval draft created" : "Eval draft updated";
    button.title = result.path || "";
    button.classList.add("done");
    setWorkspaceTab("evals");
    loadEvalCandidates();
  } catch (error) {
    button.disabled = false;
    button.textContent = originalText;
    button.title = error.message;
  }
}

function renderEvalCandidateList(candidates) {
  const container = document.getElementById("eval-candidate-list");
  if (!container) return;
  container.innerHTML = "";

  if (!Array.isArray(candidates) || !candidates.length) {
    container.appendChild(createElement("div", "muted", "No eval drafts yet."));
    return;
  }

  candidates.forEach((candidate) => {
    const item = createElement("article", "eval-candidate-item");
    const top = createElement("div", "eval-candidate-top");
    top.appendChild(createElement("span", `eval-status-pill ${candidate.status || "draft"}`, candidate.status || "draft"));
    if (candidate.feedback_issue_type) {
      top.appendChild(createElement("span", "feedback-issue-chip", feedbackIssueLabel(candidate.feedback_issue_type)));
    }
    item.appendChild(top);
    item.appendChild(createElement("strong", "", shortText(candidate.question, 90)));
    item.appendChild(createElement("span", "", shortText(candidate.expected_doc_title || candidate.doc || "No document title yet.", 90)));

    const actions = createElement("div", "feedback-review-actions");
    const editButton = createElement("button", "feedback-action-btn", "Review");
    editButton.type = "button";
    editButton.addEventListener("click", () => renderEvalCandidateEditor(candidate));
    actions.appendChild(editButton);
    item.appendChild(actions);
    container.appendChild(item);
  });
}

function fieldRow(label, element) {
  const row = createElement("label", "eval-field");
  row.appendChild(createElement("span", "", label));
  row.appendChild(element);
  return row;
}

function renderEvalCandidateEditor(candidate) {
  setWorkspaceTab("evals");
  const editor = document.getElementById("eval-candidate-editor");
  if (!editor) return;
  editor.innerHTML = "";
  editor.classList.remove("hidden");
  editor.dataset.candidateId = candidate.id;

  editor.appendChild(createElement("h3", "", `Review ${candidate.id}`));
  editor.appendChild(createElement("p", "eval-question", candidate.question || ""));

  const doc = document.createElement("input");
  doc.id = "eval-doc";
  doc.value = candidate.doc || "";
  doc.placeholder = "short doc id, for example docker";
  editor.appendChild(fieldRow("Doc", doc));

  const expectedDoc = document.createElement("input");
  expectedDoc.id = "eval-expected-doc-title";
  expectedDoc.value = candidate.expected_doc_title || "";
  expectedDoc.placeholder = "expected document title";
  editor.appendChild(fieldRow("Expected Doc", expectedDoc));

  const expectedAnswer = document.createElement("textarea");
  expectedAnswer.id = "eval-expected-answer";
  expectedAnswer.rows = 4;
  expectedAnswer.value = candidate.expected_answer || "";
  editor.appendChild(fieldRow("Expected Answer", expectedAnswer));

  const mustHave = document.createElement("textarea");
  mustHave.id = "eval-must-have";
  mustHave.rows = 4;
  mustHave.value = requirementsToText(candidate.must_have);
  editor.appendChild(fieldRow("Must Have", mustHave));

  const shouldHave = document.createElement("textarea");
  shouldHave.id = "eval-should-have";
  shouldHave.rows = 3;
  shouldHave.value = requirementsToText(candidate.should_have);
  editor.appendChild(fieldRow("Should Have", shouldHave));

  const mustNotHave = document.createElement("textarea");
  mustNotHave.id = "eval-must-not-have";
  mustNotHave.rows = 3;
  mustNotHave.value = requirementsToText(candidate.must_not_have);
  editor.appendChild(fieldRow("Must Not Have", mustNotHave));

  const predicted = createElement("details", "eval-preview");
  predicted.appendChild(createElement("summary", "", "Predicted answer"));
  predicted.appendChild(createElement("p", "", candidate.predicted_answer || ""));
  editor.appendChild(predicted);

  const status = createElement("div", "eval-editor-status", "");
  const actions = createElement("div", "eval-editor-actions");
  const saveButton = createElement("button", "feedback-action-btn", "Save draft");
  saveButton.type = "button";
  saveButton.addEventListener("click", () => saveEvalCandidate(candidate.id, status));
  actions.appendChild(saveButton);

  const promoteButton = createElement("button", "feedback-action-btn", "Promote");
  promoteButton.type = "button";
  promoteButton.addEventListener("click", () => promoteEvalCandidate(candidate.id, status));
  actions.appendChild(promoteButton);

  const runEvalButton = createElement("button", "feedback-action-btn", "Run eval");
  runEvalButton.type = "button";
  runEvalButton.addEventListener("click", () => runEvalCandidate(candidate.id, status));
  actions.appendChild(runEvalButton);

  if (candidate.trace_id) {
    const traceButton = createElement("button", "feedback-action-btn", "Open trace");
    traceButton.type = "button";
    traceButton.addEventListener("click", () => loadTrace(candidate.trace_id));
    actions.appendChild(traceButton);
  }

  editor.appendChild(actions);
  editor.appendChild(status);
  editor.appendChild(createElement("div", "eval-result-panel hidden", ""));
}

function evalCandidatePayload(status = "reviewed") {
  return {
    doc: document.getElementById("eval-doc")?.value || "",
    expected_doc_title: document.getElementById("eval-expected-doc-title")?.value || "",
    expected_answer: document.getElementById("eval-expected-answer")?.value || "",
    must_have: textToRequirements(document.getElementById("eval-must-have")?.value || ""),
    should_have: textToRequirements(document.getElementById("eval-should-have")?.value || ""),
    must_not_have: textToRequirements(document.getElementById("eval-must-not-have")?.value || ""),
    status,
  };
}

async function saveEvalCandidate(candidateId, status) {
  if (!candidateId) return;
  if (status) status.textContent = "Saving...";
  try {
    const candidate = await fetchJSON(`/api/eval-candidates/${encodeURIComponent(candidateId)}`, {
      method: "PATCH",
      body: JSON.stringify(evalCandidatePayload("reviewed")),
    });
    if (status) status.textContent = "Draft saved.";
    await loadEvalCandidates();
    renderEvalCandidateEditor(candidate);
  } catch (error) {
    if (status) status.textContent = `Save failed: ${error.message}`;
  }
}

async function promoteEvalCandidate(candidateId, status) {
  if (!candidateId) return;
  if (status) status.textContent = "Saving before promotion...";
  try {
    await fetchJSON(`/api/eval-candidates/${encodeURIComponent(candidateId)}`, {
      method: "PATCH",
      body: JSON.stringify(evalCandidatePayload("reviewed")),
    });
    if (status) status.textContent = "Promoting...";
    const result = await fetchJSON(`/api/eval-candidates/${encodeURIComponent(candidateId)}/promote`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (status) status.textContent = `Promoted to ${result.path}`;
    await loadEvalCandidates();
    renderEvalCandidateEditor(result.candidate);
  } catch (error) {
    if (status) status.textContent = `Promotion failed: ${error.message}`;
  }
}

function renderEvalRunResult(payload) {
  const panel = document.querySelector(".eval-result-panel");
  if (!panel) return;
  panel.innerHTML = "";
  panel.classList.remove("hidden");

  const result = payload.result || {};
  const score = Number(payload.score || result.score || 0);
  const tone = payload.passed ? "ok" : "bad";
  const header = createElement("div", `eval-result-header ${tone}`);
  header.appendChild(createElement("strong", "", `${score.toFixed(2)}/10`));
  header.appendChild(createElement("span", "", payload.passed ? "Passed" : "Needs work"));
  panel.appendChild(header);

  const grid = createElement("div", "eval-result-grid");
  [
    ["Fact", result.fact_score],
    ["Optional", result.optional_score],
    ["Citation", result.citation_score],
    ["Routing", result.routing_score],
    ["Verifier", result.verifier_score],
    ["Focus", result.focus_score],
  ].forEach(([label, value]) => {
    const item = createElement("div", "eval-result-metric");
    item.appendChild(createElement("span", "", label));
    item.appendChild(createElement("strong", "", formatValue(value)));
    grid.appendChild(item);
  });
  panel.appendChild(grid);

  const fields = [
    ["Missing", result.missing_must_have],
    ["Unwanted", result.triggered_must_not_have],
    ["Expected Doc", result.expected_doc_title],
    ["Top Routed Doc", result.top_routed_doc],
  ];
  fields.forEach(([label, value]) => {
    const row = createElement("div", "eval-result-row");
    row.appendChild(createElement("span", "", label));
    row.appendChild(createElement("strong", "", Array.isArray(value) ? value.join("; ") || "-" : formatValue(value)));
    panel.appendChild(row);
  });

  const answer = createElement("details", "eval-preview");
  answer.appendChild(createElement("summary", "", "Evaluated answer"));
  answer.appendChild(createElement("p", "", result.answer || ""));
  panel.appendChild(answer);
}

async function runEvalCandidate(candidateId, status) {
  if (!candidateId) return;
  if (status) status.textContent = "Running targeted eval...";
  try {
    const result = await fetchJSON(`/api/eval-candidates/${encodeURIComponent(candidateId)}/run-eval`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (status) status.textContent = `Eval complete: ${Number(result.score || 0).toFixed(2)}/10`;
    renderEvalRunResult(result);
  } catch (error) {
    if (status) status.textContent = `Eval failed: ${error.message}`;
  }
}

async function loadEvalCandidates() {
  try {
    const candidates = await fetchJSON("/api/eval-candidates?limit=8");
    renderEvalCandidateList(candidates);
  } catch (error) {
    const container = document.getElementById("eval-candidate-list");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Eval draft error: ${error.message}`));
    }
  }
}

function renderTools(tools) {
  const container = document.getElementById("tools-list");
  const summary = document.getElementById("tools-summary");
  if (!container) return;
  container.innerHTML = "";

  const allTools = Array.isArray(tools) ? tools : [];
  const filter = currentToolFilter.toLowerCase();
  const visibleTools = filter
    ? allTools.filter((tool) => {
        const haystack = [
          tool.name,
          tool.description,
          tool.source,
          tool.metadata && tool.metadata.server_name,
        ].join(" ").toLowerCase();
        return haystack.includes(filter);
      })
    : allTools;

  if (summary) {
    summary.textContent = filter
      ? `${visibleTools.length} of ${allTools.length} tools matched`
      : `${allTools.length} registered tools`;
  }

  if (!visibleTools.length) {
    container.appendChild(createElement("div", "muted", "No registered tools."));
    return;
  }

  visibleTools.forEach((tool) => {
    const item = createElement("article", "tool-list-item");
    const top = createElement("div", "tool-list-top");
    top.appendChild(createElement("strong", "", tool.name || "unknown_tool"));
    top.appendChild(createElement("span", `tool-source-pill ${tool.source || "local"}`, tool.source || "local"));
    item.appendChild(top);
    item.appendChild(createElement("p", "", shortText(tool.description, 130)));

    const meta = createElement("div", "tool-meta-row");
    meta.appendChild(
      createElement(
        "span",
        tool.requires_approval ? "tool-approval-pill warn" : "tool-approval-pill ok",
        tool.requires_approval ? "approval" : "read-only"
      )
    );
    const serverName = tool.metadata && tool.metadata.server_name;
    if (serverName) {
      meta.appendChild(createElement("span", "tool-approval-pill", serverName));
    }
    item.appendChild(meta);
    container.appendChild(item);
  });
}

async function loadTools() {
  try {
    const tools = await fetchJSON("/api/tools");
    currentTools = Array.isArray(tools) ? tools : [];
    renderTools(currentTools);
  } catch (error) {
    const container = document.getElementById("tools-list");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Tool error: ${error.message}`));
    }
  }
}

function toolAuditTone(event) {
  const status = String(event.status || "").toLowerCase();
  if (status === "allow" && event.approved) return "approved";
  if (status === "allow") return "allow";
  if (status === "needs_approval") return "needs-approval";
  if (status === "deny") return "deny";
  return "unknown";
}

function toolRiskTone(event) {
  const level = String(event.risk_level || "").toLowerCase();
  if (level === "high") return "high";
  if (level === "medium") return "medium";
  if (level === "low") return "low";
  return "unknown";
}

function renderToolAudit(payload) {
  const summary = document.getElementById("tool-audit-summary");
  const container = document.getElementById("tool-audit-list");
  if (!container) return;

  const items = Array.isArray(payload?.items) ? payload.items : [];
  const counts = payload?.summary || {};

  if (summary) {
    summary.innerHTML = "";
    const grid = createElement("div", "tool-audit-summary-grid");
    [
      ["Total", counts.total_count],
      ["Allowed", counts.allow_count],
      ["Needs approval", counts.needs_approval_count],
      ["Denied", counts.deny_count],
      ["Approved", counts.approved_count],
      ["Executed", counts.executed_count],
      ["Blocked", counts.blocked_count],
      ["High risk", counts.high_risk_count],
      ["Write/delete", counts.write_delete_count],
    ].forEach(([label, value]) => {
      const item = createElement("div", "tool-audit-summary-item");
      item.appendChild(createElement("span", "", label));
      item.appendChild(createElement("strong", "", formatValue(value)));
      grid.appendChild(item);
    });
    summary.appendChild(grid);
  }

  container.innerHTML = "";
  if (!items.length) {
    container.appendChild(createElement("div", "muted", "No guarded tool calls found in recent traces."));
    return;
  }

  items.forEach((event) => {
    const tone = toolAuditTone(event);
    const item = createElement("article", `tool-audit-item ${tone}`);

    const top = createElement("div", "tool-audit-top");
    const title = createElement("strong", "", event.tool_name || "unknown_tool");
    title.title = event.tool_name || "";
    top.appendChild(title);
    top.appendChild(createElement("span", `tool-audit-status ${tone}`, event.status || "unknown"));
    item.appendChild(top);

    const meta = createElement("div", "tool-meta-row");
    meta.appendChild(createElement("span", "tool-approval-pill", event.tool_category || "tool"));
    meta.appendChild(
      createElement(
        "span",
        `tool-risk-pill ${toolRiskTone(event)}`,
        `${event.risk_level || "unknown"} risk`
      )
    );
    meta.appendChild(createElement("span", `tool-source-pill ${event.tool_source || "local"}`, event.tool_source || "unknown"));
    meta.appendChild(
      createElement(
        "span",
        event.requires_approval ? "tool-approval-pill warn" : "tool-approval-pill ok",
        event.requires_approval ? "approval required" : "no approval"
      )
    );
    if (event.approved) {
      meta.appendChild(createElement("span", "tool-approval-pill ok", "approved"));
    }
    item.appendChild(meta);

    item.appendChild(createElement("p", "", shortText(event.query, 140)));

    const details = createElement("div", "tool-audit-details");
    renderKeyValues(details, {
      trace: `#${event.trace_id}`,
      executed: event.executed,
      success: event.success,
      reason: event.reason,
      risk: event.risk_reason,
      blocked: event.blocked,
      policy: event.policy_name,
      time: event.created_at,
    });
    item.appendChild(details);

    const actions = createElement("div", "feedback-review-actions");
    const openButton = createElement("button", "feedback-action-btn", "Open trace");
    openButton.type = "button";
    openButton.addEventListener("click", () => loadTrace(event.trace_id));
    actions.appendChild(openButton);
    item.appendChild(actions);

    container.appendChild(item);
  });
}

async function loadToolAudit() {
  const summary = document.getElementById("tool-audit-summary");
  const container = document.getElementById("tool-audit-list");
  if (summary) {
    summary.textContent = "Loading tool audit...";
  }

  try {
    const payload = await fetchJSON("/api/tools/audit?limit=50");
    renderToolAudit(payload);
  } catch (error) {
    if (summary) {
      summary.textContent = "Could not load tool audit.";
    }
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Tool audit error: ${error.message}`));
    }
  }
}

function memoryKindLabel(kind) {
  return String(kind || "memory").replace(/_/g, " ");
}

function renderMemory(payload) {
  const summary = document.getElementById("memory-summary");
  const container = document.getElementById("memory-list");
  if (!container) return;

  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (summary) {
    summary.textContent = `${items.length} memory item${items.length === 1 ? "" : "s"} for session ${payload?.session_id || "default"}`;
  }

  container.innerHTML = "";
  if (!items.length) {
    container.appendChild(createElement("div", "muted", "No long-term memory found."));
    return;
  }

  items.forEach((memory) => {
    const item = createElement("article", "memory-item");
    const top = createElement("div", "memory-item-top");
    top.appendChild(createElement("strong", "", memoryKindLabel(memory.kind)));
    top.appendChild(createElement("span", `memory-scope-pill ${memory.scope || "global"}`, memory.scope || "global"));
    item.appendChild(top);

    item.appendChild(createElement("p", "", memory.content || ""));

    const meta = createElement("div", "memory-meta-row");
    meta.appendChild(createElement("span", "", `#${memory.memory_id}`));
    meta.appendChild(createElement("span", "", memory.source || "manual"));
    meta.appendChild(createElement("span", "", `importance ${formatValue(memory.importance)}`));
    meta.appendChild(createElement("span", "", `access ${formatValue(memory.access_count)}`));
    item.appendChild(meta);

    const time = createElement("div", "memory-time-row");
    time.appendChild(createElement("span", "", `updated ${formatValue(memory.updated_at)}`));
    item.appendChild(time);

    const actions = createElement("div", "feedback-review-actions");
    const deleteButton = createElement("button", "memory-delete-btn", "Delete");
    deleteButton.type = "button";
    deleteButton.addEventListener("click", () => deleteMemoryItem(memory.memory_id, deleteButton));
    actions.appendChild(deleteButton);
    item.appendChild(actions);

    container.appendChild(item);
  });
}

async function loadMemory() {
  const summary = document.getElementById("memory-summary");
  const container = document.getElementById("memory-list");
  const sessionInput = document.getElementById("memory-session-id");
  const includeGlobal = document.getElementById("memory-include-global");
  const params = new URLSearchParams({
    session_id: sessionInput?.value.trim() || getStoredSessionId(),
    include_global: includeGlobal?.checked ? "true" : "false",
    limit: "80",
  });

  if (summary) {
    summary.textContent = "Loading memory...";
  }

  try {
    const payload = await fetchJSON(`/api/memory?${params.toString()}`);
    renderMemory(payload);
  } catch (error) {
    if (summary) {
      summary.textContent = "Could not load memory.";
    }
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Memory error: ${error.message}`));
    }
  }
}

async function deleteMemoryItem(memoryId, button) {
  if (!memoryId) return;
  if (!window.confirm(`Delete memory #${memoryId}?`)) return;

  if (button) {
    button.disabled = true;
    button.textContent = "Deleting...";
  }

  try {
    await fetchJSON(`/api/memory/${encodeURIComponent(memoryId)}`, {
      method: "DELETE",
    });
    await loadMemory();
  } catch (error) {
    if (button) {
      button.disabled = false;
      button.textContent = "Delete";
    }
    const summary = document.getElementById("memory-summary");
    if (summary) {
      summary.textContent = `Delete failed: ${error.message}`;
    }
  }
}

function renderSystemStatus(payload) {
  const summary = document.getElementById("system-summary");
  const container = document.getElementById("system-components");
  if (!container) return;

  const components = Array.isArray(payload?.components) ? payload.components : [];
  const overall = payload?.status || "unknown";
  const counts = payload?.summary || {};

  if (summary) {
    summary.innerHTML = "";
    const top = createElement("div", "system-component-top");
    top.appendChild(createElement("strong", "", "Runtime status"));
    top.appendChild(createElement("span", `system-pill ${overall}`, overall));
    summary.appendChild(top);
    summary.appendChild(
      createElement(
        "div",
        "",
        `${formatValue(counts.ok_count)} ok, ${formatValue(counts.warn_count)} warning, ${formatValue(counts.error_count)} error - ${formatValue(counts.document_count)} documents - ${formatValue(counts.tool_count)} tools`
      )
    );
  }

  container.innerHTML = "";
  if (!components.length) {
    container.appendChild(createElement("div", "muted", "No system components reported."));
    return;
  }

  components.forEach((component) => {
    const item = createElement("article", `system-component ${component.status || "warn"}`);
    const top = createElement("div", "system-component-top");
    top.appendChild(createElement("strong", "", component.name || "Component"));
    top.appendChild(createElement("span", `system-pill ${component.status || "warn"}`, component.status || "warn"));
    item.appendChild(top);
    item.appendChild(createElement("p", "system-component-message", component.message || ""));

    const details = component.details || {};
    const detailEntries = Object.entries(details).filter(([, value]) => value !== undefined && value !== null && value !== "");
    if (component.duration_ms) {
      detailEntries.unshift(["duration_ms", component.duration_ms]);
    }

    if (detailEntries.length) {
      const grid = createElement("div", "system-detail-grid");
      detailEntries.slice(0, 6).forEach(([key, value]) => {
        const label = key.replace(/_/g, " ");
        const displayValue = Array.isArray(value)
          ? shortText(value.join(", "), 120)
          : shortText(formatValue(value), 120);
        grid.appendChild(createElement("span", "", label));
        grid.appendChild(createElement("strong", "", displayValue));
      });
      item.appendChild(grid);
    }

    container.appendChild(item);
  });
}

async function loadSystemStatus() {
  const summary = document.getElementById("system-summary");
  const container = document.getElementById("system-components");
  if (summary) {
    summary.textContent = "Checking system status...";
  }

  try {
    const status = await fetchJSON("/api/system/status");
    renderSystemStatus(status);
  } catch (error) {
    if (summary) {
      summary.textContent = "Could not load system status.";
    }
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `System status error: ${error.message}`));
    }
  }
}

function ingestionStatusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "indexed" || normalized === "skipped") return "ok";
  if (normalized === "running") return "warn";
  if (normalized === "failed") return "bad";
  return "warn";
}

function renderIngestionStatus(payload) {
  const summary = document.getElementById("ingestion-status-summary");
  const container = document.getElementById("ingestion-status-list");
  if (!container) return;

  const items = Array.isArray(payload?.items) ? payload.items : [];
  const counts = payload?.summary || {};
  const activeFilter = payload?.status || "";

  if (summary) {
    summary.innerHTML = "";
    const grid = createElement("div", "ingestion-summary-grid");
    [
      ["Total", counts.total_count],
      ["Indexed", counts.indexed_count],
      ["Skipped", counts.skipped_count],
      ["Failed", counts.failed_count],
      ["Running", counts.running_count],
    ].forEach(([label, value]) => {
      const card = createElement("div", "ingestion-summary-card");
      card.appendChild(createElement("span", "", label));
      card.appendChild(createElement("strong", "", formatValue(value)));
      grid.appendChild(card);
    });
    summary.appendChild(grid);
    if (activeFilter) {
      summary.appendChild(createElement("div", "ingestion-filter-note", `Showing ${activeFilter} records`));
    }
  }

  container.innerHTML = "";
  if (!items.length) {
    container.appendChild(createElement("div", "muted", "No ingestion status records found."));
    return;
  }

  items.forEach((record) => {
    const tone = ingestionStatusTone(record.status);
    const item = createElement("article", `ingestion-status-item ${tone}`);
    const top = createElement("div", "ingestion-status-top");
    const title = record.title || sourceFileName(record.source_path);
    top.appendChild(createElement("strong", "", title || "Untitled"));
    top.appendChild(createElement("span", `ingestion-status-pill ${tone}`, record.status || "unknown"));
    item.appendChild(top);

    const fileName = createElement("div", "ingestion-source-path", sourceFileName(record.source_path));
    fileName.title = record.source_path || "";
    item.appendChild(fileName);

    const meta = createElement("div", "ingestion-meta-grid");
    [
      ["Pages", record.page_count],
      ["Chunks", record.chunk_count],
      ["Parser", record.parser_version || "legacy"],
      ["Chunking", record.chunking_version || "legacy"],
      ["Embed", record.embedding_model],
      ["Completed", record.completed_at || record.started_at],
    ].forEach(([label, value]) => {
      meta.appendChild(createElement("span", "", label));
      meta.appendChild(createElement("strong", "", shortText(formatValue(value), 90)));
    });
    item.appendChild(meta);

    if (record.error) {
      item.appendChild(createElement("div", "ingestion-error-text", shortText(record.error, 260)));
    }

    container.appendChild(item);
  });
}

async function loadIngestionStatus() {
  const summary = document.getElementById("ingestion-status-summary");
  const container = document.getElementById("ingestion-status-list");
  const filter = document.getElementById("ingestion-status-filter");
  const params = new URLSearchParams({ limit: "50" });
  if (filter && filter.value) {
    params.set("status", filter.value);
  }

  if (summary) {
    summary.textContent = "Loading ingestion status...";
  }

  try {
    const payload = await fetchJSON(`/api/ingestion/status?${params.toString()}`);
    renderIngestionStatus(payload);
  } catch (error) {
    if (summary) {
      summary.textContent = "Could not load ingestion status.";
    }
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Ingestion status error: ${error.message}`));
    }
  }
}

function renderDocuments(payload, append = false) {
  const container = document.getElementById("documents-list");
  const summary = document.getElementById("document-summary");
  const loadMore = document.getElementById("load-docs-btn");
  if (!container) return;

  const docs = Array.isArray(payload?.items) ? payload.items : [];
  const total = Number(payload?.total || 0);
  const offset = Number(payload?.offset || 0);

  if (!append) {
    container.innerHTML = "";
  }

  if (summary) {
    const shown = Math.min(offset + docs.length, total);
    summary.textContent = documentQuery
      ? `${shown} of ${total} matching documents`
      : `${total} indexed documents`;
  }

  if (!docs.length && !append) {
    container.appendChild(createElement("div", "muted", "No matching documents found."));
  }

  if (loadMore) {
    const nextOffset = offset + docs.length;
    const hasMore = nextOffset < total;
    loadMore.classList.toggle("hidden", !hasMore);
    loadMore.textContent = hasMore ? `Load more (${nextOffset}/${total})` : "Load more";
    loadMore.disabled = !hasMore;
  }

  for (const doc of docs) {
    const item = document.createElement("div");
    item.className = "doc-item";

    item.appendChild(createElement("div", "doc-title", doc.title || "Untitled"));
    item.appendChild(documentMetaRow("Pages", doc.page_count));
    item.appendChild(documentMetaRow("Chunks", doc.chunk_count));
    item.appendChild(documentMetaRow("Status", doc.ingestion_status || "indexed"));
    item.appendChild(documentMetaRow("Parser", doc.parser_version || "legacy"));
    item.appendChild(documentMetaRow("Chunking", doc.chunking_version || "legacy"));
    item.appendChild(documentMetaRow("Path", sourceFileName(doc.source_path)));
    item.appendChild(documentMetaRow("Indexed", doc.indexed_at));
    item.title = doc.source_path || "";
    container.appendChild(item);
  }

  documentOffset = offset + docs.length;
}

function documentMetaRow(label, value) {
  const row = createElement("div", "doc-meta");
  row.appendChild(createElement("strong", "", `${label}: `));
  row.appendChild(document.createTextNode(formatValue(value)));
  return row;
}

async function loadDocuments(options = {}) {
  const append = Boolean(options.append);
  const offset = append ? documentOffset : 0;
  const params = new URLSearchParams({
    limit: String(DOCUMENT_PAGE_SIZE),
    offset: String(offset),
  });
  if (documentQuery) {
    params.set("q", documentQuery);
  }

  try {
    const payload = await fetchJSON(`/api/library/documents?${params.toString()}`);
    renderDocuments(payload, append);
  } catch (error) {
    const container = document.getElementById("documents-list");
    const summary = document.getElementById("document-summary");
    if (summary) {
      summary.textContent = "Could not load library.";
    }
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Error loading documents: ${error.message}`));
    }
  }
}

function scheduleDocumentSearch() {
  window.clearTimeout(scheduleDocumentSearch.timer);
  scheduleDocumentSearch.timer = window.setTimeout(() => {
    const input = document.getElementById("document-search");
    documentQuery = input ? input.value.trim() : "";
    documentOffset = 0;
    loadDocuments();
  }, 220);
}

function applyToolSearch() {
  const input = document.getElementById("tool-search");
  currentToolFilter = input ? input.value.trim() : "";
  renderTools(currentTools);
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  if (!input) return;

  const query = input.value.trim();
  if (!query) return;

  addMessage("User", query);
  input.value = "";
  setSendButtonLoading(true);

  try {
    const data = await fetchJSON("/api/chat", {
      method: "POST",
      body: JSON.stringify({ query }),
    });

    addAssistantResponse(data.answer, data.trace_id, data.citations || [], {
      query,
      approval: {
        needsApproval: data.needs_approval,
        toolName: data.approval_tool_name,
        reason: data.approval_reason,
      },
    });
  } catch (error) {
    addMessage("Assistant", `Error: ${error.message}`, "error-message");
  } finally {
    setSendButtonLoading(false);
  }
}

async function ingestPath() {
  const input = document.getElementById("ingest-path");
  const statusBox = document.getElementById("ingest-status");
  const forceInput = document.getElementById("ingest-force");

  if (!input || !statusBox) return;

  const path = input.value.trim();
  if (!path) {
    statusBox.textContent = "Enter a file or folder path first.";
    statusBox.className = "status-box error-text";
    return;
  }

  setIngestLoading(true);
  statusBox.textContent = "Ingestion in progress...";
  statusBox.className = "status-box";

  try {
    const data = await fetchJSON("/api/ingest-path", {
      method: "POST",
      body: JSON.stringify({
        path,
        force: Boolean(forceInput && forceInput.checked),
      }),
    });

    const lines = [
      `Success: ${data.success_count}`,
      `Skipped: ${data.skipped_count || 0}`,
      `Failed: ${data.failed_count}`,
      "",
      ...data.results.map((r) => {
        const status = r.status || (r.success ? "indexed" : "failed");
        const prefix = status === "skipped" ? "[SKIP]" : r.success ? "[OK]" : "[FAIL]";
        const counts = r.page_count || r.chunk_count
          ? ` pages=${formatValue(r.page_count)} chunks=${formatValue(r.chunk_count)}`
          : "";
        return `${prefix} ${r.file_name}${counts} - ${r.message}`;
      }),
    ];

    statusBox.textContent = lines.join("\n");
    statusBox.className = "status-box";
    await loadDocuments();
    await loadIngestionStatus();
  } catch (error) {
    statusBox.textContent = `Error: ${error.message}`;
    statusBox.className = "status-box error-text";
  } finally {
    setIngestLoading(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const sendBtn = document.getElementById("send-btn");
  const refreshDocsBtn = document.getElementById("refresh-docs-btn");
  const refreshToolsBtn = document.getElementById("refresh-tools-btn");
  const refreshToolAuditBtn = document.getElementById("refresh-tool-audit-btn");
  const refreshMemoryBtn = document.getElementById("refresh-memory-btn");
  const refreshSystemBtn = document.getElementById("refresh-system-btn");
  const refreshIngestionStatusBtn = document.getElementById("refresh-ingestion-status-btn");
  const refreshTracesBtn = document.getElementById("refresh-traces-btn");
  const refreshEvalCandidatesBtn = document.getElementById("refresh-eval-candidates-btn");
  const feedbackFilterBtns = document.querySelectorAll(".feedback-filter-btn");
  const workspaceTabs = document.querySelectorAll(".workspace-tab");
  const documentSearch = document.getElementById("document-search");
  const loadDocsBtn = document.getElementById("load-docs-btn");
  const toolSearch = document.getElementById("tool-search");
  const ingestionStatusFilter = document.getElementById("ingestion-status-filter");
  const ingestBtn = document.getElementById("ingest-btn");
  const chatInput = document.getElementById("chat-input");
  const saveAccessBtn = document.getElementById("save-access-btn");

  loadAccessSettings();

  if (sendBtn) {
    sendBtn.addEventListener("click", sendChat);
  }

  if (saveAccessBtn) {
    saveAccessBtn.addEventListener("click", saveAccessSettings);
  }

  if (refreshDocsBtn) {
    refreshDocsBtn.addEventListener("click", () => loadDocuments());
  }

  if (refreshToolsBtn) {
    refreshToolsBtn.addEventListener("click", loadTools);
  }

  if (refreshToolAuditBtn) {
    refreshToolAuditBtn.addEventListener("click", loadToolAudit);
  }

  if (refreshMemoryBtn) {
    refreshMemoryBtn.addEventListener("click", loadMemory);
  }

  if (refreshSystemBtn) {
    refreshSystemBtn.addEventListener("click", loadSystemStatus);
  }

  if (refreshIngestionStatusBtn) {
    refreshIngestionStatusBtn.addEventListener("click", loadIngestionStatus);
  }

  if (refreshTracesBtn) {
    refreshTracesBtn.addEventListener("click", () => {
      loadRecentTraces();
      loadFeedbackSummary();
      loadFeedbackItems();
      loadEvalCandidates();
      loadSystemStatus();
      loadIngestionStatus();
      loadToolAudit();
      loadMemory();
    });
  }

  if (refreshEvalCandidatesBtn) {
    refreshEvalCandidatesBtn.addEventListener("click", loadEvalCandidates);
  }

  feedbackFilterBtns.forEach((button) => {
    button.addEventListener("click", () => setFeedbackFilter(button.dataset.feedbackFilter || "all"));
  });

  workspaceTabs.forEach((button) => {
    button.addEventListener("click", () => setWorkspaceTab(button.dataset.workspaceTab || "trace"));
  });

  if (documentSearch) {
    documentSearch.addEventListener("input", scheduleDocumentSearch);
  }

  if (loadDocsBtn) {
    loadDocsBtn.addEventListener("click", () => loadDocuments({ append: true }));
  }

  if (toolSearch) {
    toolSearch.addEventListener("input", applyToolSearch);
  }

  if (ingestionStatusFilter) {
    ingestionStatusFilter.addEventListener("change", loadIngestionStatus);
  }

  const memorySessionInput = document.getElementById("memory-session-id");
  const memoryIncludeGlobal = document.getElementById("memory-include-global");
  if (memorySessionInput) {
    memorySessionInput.addEventListener("change", loadMemory);
  }
  if (memoryIncludeGlobal) {
    memoryIncludeGlobal.addEventListener("change", loadMemory);
  }

  if (ingestBtn) {
    ingestBtn.addEventListener("click", ingestPath);
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendChat();
      }
    });
  }

  loadDocuments();
  loadTools();
  loadToolAudit();
  loadMemory();
  loadSystemStatus();
  loadIngestionStatus();
  loadRecentTraces();
  loadFeedbackSummary();
  loadFeedbackItems();
  loadEvalCandidates();
});

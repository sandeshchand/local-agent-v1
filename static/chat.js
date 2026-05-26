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

  if (ingestBtn) {
    ingestBtn.disabled = isLoading;
    ingestBtn.textContent = isLoading ? "Ingesting..." : "Ingest";
  }

  if (ingestInput) {
    ingestInput.disabled = isLoading;
  }
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
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
  const box = createElement("section", "sources-box");
  const header = createElement("div", "sources-header");
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

function addAssistantResponse(answer, traceId, citations = []) {
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

  if (Array.isArray(citations) && citations.length > 0) {
    body.appendChild(renderSourcesBox(citations));
  }

  body.appendChild(renderFeedbackControls(traceId));

  const traceRow = document.createElement("div");
  traceRow.className = "trace-action-row";

  const trace = document.createElement("button");
  trace.type = "button";
  trace.className = "trace-badge";
  trace.textContent = `Trace ${traceId}`;
  trace.addEventListener("click", () => loadTrace(traceId));
  traceRow.appendChild(trace);
  body.appendChild(traceRow);

  wrapper.appendChild(role);
  wrapper.appendChild(body);
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  loadTrace(traceId);
  loadRecentTraces();
}

function metric(label, value, tone = "") {
  const item = createElement("div", `trace-metric ${tone}`);
  item.appendChild(createElement("span", "trace-metric-label", label));
  item.appendChild(createElement("strong", "", formatValue(value)));
  return item;
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
  const steps = document.getElementById("trace-steps");
  const evidence = document.getElementById("trace-evidence");
  const tools = document.getElementById("trace-tools");
  const raw = document.getElementById("trace-raw-json");

  if (!detail || !empty || !metrics || !steps || !evidence || !tools || !raw) return;

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

function renderDocuments(docs) {
  const container = document.getElementById("documents-list");
  if (!container) return;

  container.innerHTML = "";

  if (!docs.length) {
    container.innerHTML = `<div class="muted">No indexed documents found.</div>`;
    return;
  }

  for (const doc of docs) {
    const item = document.createElement("div");
    item.className = "doc-item";
    item.innerHTML = `
      <div class="doc-title">${doc.title}</div>
      <div class="doc-meta"><strong>Pages:</strong> ${doc.page_count}</div>
      <div class="doc-meta"><strong>Path:</strong> ${doc.source_path}</div>
      <div class="doc-meta"><strong>Indexed:</strong> ${doc.indexed_at}</div>
    `;
    container.appendChild(item);
  }
}

async function loadDocuments() {
  try {
    const docs = await fetchJSON("/api/documents");
    renderDocuments(docs);
  } catch (error) {
    const container = document.getElementById("documents-list");
    if (container) {
      container.innerHTML = `<div class="error-text">Error loading documents: ${error.message}</div>`;
    }
  }
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

    addAssistantResponse(data.answer, data.trace_id, data.citations || []);
  } catch (error) {
    addMessage("Assistant", `Error: ${error.message}`, "error-message");
  } finally {
    setSendButtonLoading(false);
  }
}

async function ingestPath() {
  const input = document.getElementById("ingest-path");
  const statusBox = document.getElementById("ingest-status");

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
      body: JSON.stringify({ path }),
    });

    const lines = [
      `Success: ${data.success_count}`,
      `Failed: ${data.failed_count}`,
      "",
      ...data.results.map((r) =>
        `${r.success ? "[OK]" : "[FAIL]"} ${r.file_name} - ${r.message}`
      ),
    ];

    statusBox.textContent = lines.join("\n");
    statusBox.className = "status-box";
    await loadDocuments();
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
  const refreshTracesBtn = document.getElementById("refresh-traces-btn");
  const ingestBtn = document.getElementById("ingest-btn");
  const chatInput = document.getElementById("chat-input");

  if (sendBtn) {
    sendBtn.addEventListener("click", sendChat);
  }

  if (refreshDocsBtn) {
    refreshDocsBtn.addEventListener("click", loadDocuments);
  }

  if (refreshTracesBtn) {
    refreshTracesBtn.addEventListener("click", loadRecentTraces);
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
  loadRecentTraces();
});

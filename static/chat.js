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
  if (!container) return;
  container.innerHTML = "";

  if (!Array.isArray(tools) || !tools.length) {
    container.appendChild(createElement("div", "muted", "No registered tools."));
    return;
  }

  tools.forEach((tool) => {
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
    renderTools(tools);
  } catch (error) {
    const container = document.getElementById("tools-list");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Tool error: ${error.message}`));
    }
  }
}

function renderDocuments(docs) {
  const container = document.getElementById("documents-list");
  if (!container) return;

  container.innerHTML = "";

  if (!docs.length) {
    container.appendChild(createElement("div", "muted", "No indexed documents found."));
    return;
  }

  for (const doc of docs) {
    const item = document.createElement("div");
    item.className = "doc-item";

    item.appendChild(createElement("div", "doc-title", doc.title || "Untitled"));
    item.appendChild(documentMetaRow("Pages", doc.page_count));
    item.appendChild(documentMetaRow("Path", doc.source_path));
    item.appendChild(documentMetaRow("Indexed", doc.indexed_at));
    container.appendChild(item);
  }
}

function documentMetaRow(label, value) {
  const row = createElement("div", "doc-meta");
  row.appendChild(createElement("strong", "", `${label}: `));
  row.appendChild(document.createTextNode(formatValue(value)));
  return row;
}

async function loadDocuments() {
  try {
    const docs = await fetchJSON("/api/documents");
    renderDocuments(docs);
  } catch (error) {
    const container = document.getElementById("documents-list");
    if (container) {
      container.innerHTML = "";
      container.appendChild(createElement("div", "error-text", `Error loading documents: ${error.message}`));
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
  const refreshToolsBtn = document.getElementById("refresh-tools-btn");
  const refreshTracesBtn = document.getElementById("refresh-traces-btn");
  const refreshEvalCandidatesBtn = document.getElementById("refresh-eval-candidates-btn");
  const feedbackFilterBtns = document.querySelectorAll(".feedback-filter-btn");
  const workspaceTabs = document.querySelectorAll(".workspace-tab");
  const ingestBtn = document.getElementById("ingest-btn");
  const chatInput = document.getElementById("chat-input");

  if (sendBtn) {
    sendBtn.addEventListener("click", sendChat);
  }

  if (refreshDocsBtn) {
    refreshDocsBtn.addEventListener("click", loadDocuments);
  }

  if (refreshToolsBtn) {
    refreshToolsBtn.addEventListener("click", loadTools);
  }

  if (refreshTracesBtn) {
    refreshTracesBtn.addEventListener("click", () => {
      loadRecentTraces();
      loadFeedbackSummary();
      loadFeedbackItems();
      loadEvalCandidates();
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
  loadRecentTraces();
  loadFeedbackSummary();
  loadFeedbackItems();
  loadEvalCandidates();
});

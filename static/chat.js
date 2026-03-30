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
    const citationTitle = document.createElement("div");
    citationTitle.className = "citation-title";
    citationTitle.textContent = "Sources";
    body.appendChild(citationTitle);

    const citationList = document.createElement("div");
    citationList.className = "citation-list";

    citations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "citation-item";
      item.innerHTML = `
        <div><strong>[${c.index}] ${c.title}</strong></div>
        <div>Page: ${c.page_number}</div>
        <div class="citation-path">${c.source_path}</div>
      `;
      citationList.appendChild(item);
    });

    body.appendChild(citationList);
  }

  const trace = document.createElement("div");
  trace.className = "trace-badge";
  trace.textContent = `Trace ID: ${traceId}`;
  body.appendChild(trace);

  wrapper.appendChild(role);
  wrapper.appendChild(body);
  chatWindow.appendChild(wrapper);
  chatWindow.scrollTop = chatWindow.scrollHeight;
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
  const ingestBtn = document.getElementById("ingest-btn");
  const chatInput = document.getElementById("chat-input");

  if (sendBtn) {
    sendBtn.addEventListener("click", sendChat);
  }

  if (refreshDocsBtn) {
    refreshDocsBtn.addEventListener("click", loadDocuments);
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
});
console.log("chat.js loaded");

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

function addMessage(role, content) {
  const template = document.getElementById("message-template");
  const chatWindow = document.getElementById("chat-window");

  if (!template || !chatWindow) {
    console.error("message-template or chat-window not found");
    return;
  }

  const clone = template.content.cloneNode(true);
  const roleEl = clone.querySelector(".message-role");
  const bodyEl = clone.querySelector(".message-body");
  const messageEl = clone.querySelector(".message");

  if (!roleEl || !bodyEl || !messageEl) {
    console.error("message template structure is invalid");
    return;
  }

  roleEl.textContent = role;
  bodyEl.textContent = content;

  if (role.toLowerCase() === "user") {
    messageEl.classList.add("user");
  } else {
    messageEl.classList.add("assistant");
  }

  chatWindow.appendChild(clone);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function renderDocuments(docs) {
  const container = document.getElementById("documents-list");
  if (!container) {
    console.error("documents-list not found");
    return;
  }

  container.innerHTML = "";

  if (!docs.length) {
    container.textContent = "No indexed documents found.";
    return;
  }

  for (const doc of docs) {
    const item = document.createElement("div");
    item.className = "doc-item";
    item.innerHTML = `
      <div class="doc-title">${doc.title}</div>
      <div class="doc-meta">Pages: ${doc.page_count}</div>
      <div class="doc-meta">${doc.source_path}</div>
      <div class="doc-meta">Indexed: ${doc.indexed_at}</div>
    `;
    container.appendChild(item);
  }
}

async function loadDocuments() {
  console.log("loading documents...");
  try {
    const docs = await fetchJSON("/api/documents");
    console.log("documents loaded", docs);
    renderDocuments(docs);
  } catch (error) {
    console.error("loadDocuments error:", error);
    const container = document.getElementById("documents-list");
    if (container) {
      container.textContent = `Error loading documents: ${error.message}`;
    }
  }
}

async function sendChat() {
  console.log("sendChat triggered");

  const input = document.getElementById("chat-input");
  if (!input) {
    console.error("chat-input not found");
    return;
  }

  const query = input.value.trim();
  if (!query) return;

  addMessage("User", query);
  input.value = "";

  try {
    const data = await fetchJSON("/api/chat", {
      method: "POST",
      body: JSON.stringify({ query }),
    });

    let citationBlock = "";
    if (Array.isArray(data.citations) && data.citations.length) {
      citationBlock =
        "\n\nCitations:\n" +
        data.citations
          .map((c) => `[${c.index}] ${c.title}, page ${c.page_number}`)
          .join("\n");
    }

    addMessage("Assistant", `${data.answer}\n\nTrace ID: ${data.trace_id}${citationBlock}`);
  } catch (error) {
    console.error("sendChat error:", error);
    addMessage("Assistant", `Error: ${error.message}`);
  }
}

async function ingestPath() {
  console.log("ingestPath triggered");

  const input = document.getElementById("ingest-path");
  const statusBox = document.getElementById("ingest-status");

  if (!input || !statusBox) {
    console.error("ingest input/status elements not found");
    return;
  }

  const path = input.value.trim();
  if (!path) {
    statusBox.textContent = "Enter a file or folder path first.";
    return;
  }

  statusBox.textContent = "Ingesting...";

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
    await loadDocuments();
  } catch (error) {
    console.error("ingestPath error:", error);
    statusBox.textContent = `Error: ${error.message}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  console.log("DOMContentLoaded");

  const sendBtn = document.getElementById("send-btn");
  const refreshDocsBtn = document.getElementById("refresh-docs-btn");
  const ingestBtn = document.getElementById("ingest-btn");
  const chatInput = document.getElementById("chat-input");

  if (sendBtn) {
    sendBtn.addEventListener("click", sendChat);
  } else {
    console.error("send-btn not found");
  }

  if (refreshDocsBtn) {
    refreshDocsBtn.addEventListener("click", loadDocuments);
  } else {
    console.error("refresh-docs-btn not found");
  }

  if (ingestBtn) {
    ingestBtn.addEventListener("click", ingestPath);
  } else {
    console.error("ingest-btn not found");
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendChat();
      }
    });
  } else {
    console.error("chat-input not found");
  }

  loadDocuments();
});
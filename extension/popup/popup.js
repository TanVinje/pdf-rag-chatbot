// ============================================
// PDF RAG Chatbot — Popup Logic
// ============================================

const DEFAULT_BACKEND_URL = "http://localhost:8000";

// DOM elements
const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const backendUrlInput = document.getElementById("backend-url");
const saveSettingsBtn = document.getElementById("save-settings-btn");
const settingsStatus = document.getElementById("settings-status");
const chatMessages = document.getElementById("chat-messages");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const uploadBtn = document.getElementById("upload-btn");
const fileInput = document.getElementById("file-input");

let backendUrl = DEFAULT_BACKEND_URL;

// ---- Initialization ----

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  questionInput.focus();
});

async function loadSettings() {
  try {
    const data = await chrome.storage.local.get(["backendUrl"]);
    if (data.backendUrl) {
      backendUrl = data.backendUrl;
      backendUrlInput.value = backendUrl;
    } else {
      backendUrlInput.value = DEFAULT_BACKEND_URL;
    }
  } catch {
    backendUrlInput.value = DEFAULT_BACKEND_URL;
  }
}

// ---- Settings ----

settingsBtn.addEventListener("click", () => {
  settingsPanel.classList.toggle("hidden");
});

saveSettingsBtn.addEventListener("click", async () => {
  const url = backendUrlInput.value.trim().replace(/\/+$/, "");
  if (!url) {
    showSettingsStatus("Please enter a valid URL.", "error");
    return;
  }

  backendUrl = url;
  await chrome.storage.local.set({ backendUrl });
  showSettingsStatus("Settings saved!", "success");

  // Quick health check
  try {
    const resp = await fetch(`${backendUrl}/health`, { method: "GET" });
    if (resp.ok) {
      const data = await resp.json();
      showSettingsStatus(
        `Connected! ${data.document_count} document(s) indexed.`,
        "success"
      );
    } else {
      showSettingsStatus("Backend responded with an error.", "error");
    }
  } catch {
    showSettingsStatus("Cannot reach backend. Is it running?", "error");
  }
});

function showSettingsStatus(msg, type) {
  settingsStatus.textContent = msg;
  settingsStatus.className = `settings-status ${type}`;
  setTimeout(() => {
    settingsStatus.textContent = "";
    settingsStatus.className = "settings-status";
  }, 4000);
}

// ---- Chat ----

sendBtn.addEventListener("click", sendQuestion);
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
});

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;

  // Clear welcome message if present
  const welcome = chatMessages.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  // Add user message
  appendMessage(question, "user");
  questionInput.value = "";
  setInputState(false);

  // Show loading
  const loadingEl = appendLoading();

  try {
    const resp = await fetch(`${backendUrl}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    loadingEl.remove();

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: "Unknown error" }));
      appendMessage(err.detail || "Something went wrong.", "bot");
    } else {
      const data = await resp.json();
      appendBotMessage(data.answer, data.citations || []);
    }
  } catch (err) {
    loadingEl.remove();
    appendMessage(
      "Could not connect to the backend. Make sure it is running.",
      "bot"
    );
  }

  setInputState(true);
  questionInput.focus();
}

// ---- File Upload ----

uploadBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async () => {
  const files = fileInput.files;
  if (!files || files.length === 0) return;

  // Clear welcome message if present
  const welcome = chatMessages.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  const fileNames = Array.from(files).map((f) => f.name).join(", ");
  appendMessage(`Uploading: ${fileNames}`, "system");
  setInputState(false);

  const loadingEl = appendLoading();

  try {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }

    const resp = await fetch(`${backendUrl}/ingest`, {
      method: "POST",
      body: formData,
    });

    loadingEl.remove();

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: "Upload failed" }));
      appendMessage(err.detail || "Failed to upload PDFs.", "bot");
    } else {
      const data = await resp.json();
      appendMessage(
        `${data.message} (${data.total_chunks} chunks indexed)`,
        "system"
      );
    }
  } catch {
    loadingEl.remove();
    appendMessage(
      "Could not connect to the backend. Make sure it is running.",
      "bot"
    );
  }

  fileInput.value = "";
  setInputState(true);
  questionInput.focus();
});

// ---- DOM Helpers ----

function appendMessage(text, type) {
  const div = document.createElement("div");
  div.className = `message ${type}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function appendBotMessage(answer, citations) {
  const div = document.createElement("div");
  div.className = "message bot";

  const answerP = document.createElement("p");
  answerP.textContent = answer;
  div.appendChild(answerP);

  if (citations && citations.length > 0) {
    const citationsDiv = document.createElement("div");
    citationsDiv.className = "citations";

    const title = document.createElement("div");
    title.className = "citations-title";
    title.textContent = "Sources";
    citationsDiv.appendChild(title);

    citations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "citation-item";
      item.innerHTML = `<span class="citation-source">${escapeHtml(c.pdf_name)}</span>, Page ${c.page}`;
      citationsDiv.appendChild(item);
    });

    div.appendChild(citationsDiv);
  }

  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function appendLoading() {
  const div = document.createElement("div");
  div.className = "message bot";
  div.innerHTML =
    '<div class="loading-dots"><span></span><span></span><span></span></div>';
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setInputState(enabled) {
  questionInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
  uploadBtn.disabled = !enabled;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

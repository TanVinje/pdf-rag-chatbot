// ============================================
// Nexzoneo Support Chatbot — Popup Logic
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

let backendUrl = DEFAULT_BACKEND_URL;

// ---- Initialization ----

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  
  // Show greeting message on load
  appendMessage("Welcome to Nexzoneo Support! How can we help you today?", "bot");
  
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
      "Could not connect to our support service. Please try again later.",
      "bot"
    );
  }

  setInputState(true);
  questionInput.focus();
}

// ---- DOM Helpers ----

function appendMessage(text, type) {
  if (type === "bot") {
    const wrapper = document.createElement("div");
    wrapper.className = "message-wrapper bot-wrapper";

    const avatar = document.createElement("div");
    avatar.className = "bot-avatar";
    avatar.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><path d="M8 15s1.5 2 4 2 4-2 4-2"/><rect x="5" y="4" width="14" height="16" rx="3" ry="3"/><path d="M9 2v2m6-2v2"/></svg>';

    const div = document.createElement("div");
    div.className = `message ${type}`;
    div.textContent = text;

    wrapper.appendChild(avatar);
    wrapper.appendChild(div);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
  } else {
    const div = document.createElement("div");
    div.className = `message ${type}`;
    div.textContent = text;
    chatMessages.appendChild(div);
    scrollToBottom();
    return div;
  }
}

function appendBotMessage(answer, citations) {
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper bot-wrapper";

  const avatar = document.createElement("div");
  avatar.className = "bot-avatar";
  avatar.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><path d="M12 8V12l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>';

  const div = document.createElement("div");
  div.className = "message bot";

  const answerP = document.createElement("p");
  answerP.innerHTML = linkify(escapeHtml(answer));
  div.appendChild(answerP);

  wrapper.appendChild(avatar);
  wrapper.appendChild(div);
  chatMessages.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function linkify(text) {
  // Turn URLs into clickable links
  return text.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>'
  );
}

function appendLoading() {
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper bot-wrapper";

  const avatar = document.createElement("div");
  avatar.className = "bot-avatar";
  avatar.innerHTML = '<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="16" cy="16" r="14" fill="white" opacity="0.2"/><path d="M16 8c-4.4 0-8 3.6-8 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8z" fill="white" opacity="0.9"/><circle cx="13" cy="15" r="1.5" fill="currentColor"/><circle cx="19" cy="15" r="1.5" fill="currentColor"/><path d="M13 19c0 0 1 1.5 3 1.5s3-1.5 3-1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M12 12l-2-2M20 12l2-2" stroke="white" stroke-width="1.5" stroke-linecap="round"/></svg>';

  const div = document.createElement("div");
  div.className = "message bot";
  div.innerHTML =
    '<div class="loading-dots"><span></span><span></span><span></span></div>';

  wrapper.appendChild(avatar);
  wrapper.appendChild(div);
  chatMessages.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setInputState(enabled) {
  questionInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

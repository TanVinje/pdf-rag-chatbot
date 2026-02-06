// Service worker for PDF RAG Chatbot extension

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    // Set default settings on first install
    chrome.storage.local.set({
      backendUrl: "http://localhost:8000",
    });
    console.log("PDF RAG Chatbot extension installed. Default settings applied.");
  }
});

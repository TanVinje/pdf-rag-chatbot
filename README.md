# PDF RAG Chatbot

An AI-powered chatbot Chrome extension that answers questions from your uploaded PDF documents using Retrieval-Augmented Generation (RAG).

## Features

- **PDF Upload** — Upload one or more PDF files for indexing
- **Smart Q&A** — Ask natural language questions about your documents
- **Citations** — Every answer includes source references (file name + page number)
- **Document-Grounded** — Refuses to answer questions not covered by the uploaded documents
- **Persistent Storage** — ChromaDB stores embeddings on disk between restarts

## Architecture

```
Chrome Extension  →  FastAPI Backend  →  ChromaDB (vectors)
     (popup)            ↕                     ↕
                   OpenAI API            PDF Processing
                  (chat + embed)         (pypdf + chunking)
```

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start the server
python -m app.main
```

The backend will start at `http://localhost:8000`. You can verify it's running by visiting `http://localhost:8000/health`.

### 2. Chrome Extension Setup

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in the top right)
3. Click **Load unpacked** and select the `extension/` directory
4. The PDF Chatbot icon will appear in your toolbar

### 3. Usage

1. Click the extension icon to open the popup
2. Click the **upload button** (arrow icon) to select one or more PDF files
3. Wait for the files to be ingested (you'll see a confirmation message)
4. Type a question in the input field and press **Enter** or click **Send**
5. The chatbot will answer based on the uploaded documents, with citations

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `CHROMA_PATH` | `./chroma_db` | Path for ChromaDB persistent storage |
| `SIMILARITY_THRESHOLD` | `0.25` | Minimum similarity score for retrieval |
| `TOP_K` | `6` | Number of top chunks to retrieve |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | OpenAI model for chat completions |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI model for embeddings |
| `HOST` | `0.0.0.0` | Backend host |
| `PORT` | `8000` | Backend port |

### Extension Settings

Click the **gear icon** in the extension popup to change the backend URL (default: `http://localhost:8000`).

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ingest` | [Admin Only] Upload PDF files for indexing |
| `POST` | `/chat` | Ask a question about uploaded documents |
| `GET` | `/health` | Health check with document count |
| `POST` | `/clear` | [Admin Only] Clear entire knowledge base |
| `GET` | `/logs` | [Admin Only] View unanswered questions log |

### Admin Endpoints

Admin endpoints require a `Authorization: Bearer <ADMIN_SECRET>` header. Set `ADMIN_SECRET` in your `.env` file.

**GET /logs** - View questions the bot couldn't answer (helps identify knowledge gaps)

Query parameters:
- `limit` (optional, default: 50): Number of log entries to return

Response includes:
- `timestamp`: When the question was asked
- `question`: The user's question
- `reason`: Why it couldn't be answered (`no_documents`, `low_similarity`, `llm_error`)
- `similarity_score`: Best match score (if applicable)

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app + endpoints
│   ├── config.py            # Settings + environment
│   ├── services/
│   │   ├── pdf_processor.py # PDF extraction + chunking
│   │   ├── vector_store.py  # ChromaDB operations
│   │   └── rag_service.py   # RAG logic + LLM calls
│   └── models/
│       └── schemas.py       # Pydantic models
├── requirements.txt
└── .env.example

extension/
├── manifest.json            # Manifest v3
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
├── background.js            # Service worker
└── icons/
    └── icon*.svg
```

## Embedding Fallback

If no `OPENAI_API_KEY` is set, the backend automatically falls back to local `sentence-transformers/all-MiniLM-L6-v2` embeddings. Note that the chat endpoint still requires an OpenAI API key to function.

## Tech Stack

- **Backend:** Python, FastAPI, ChromaDB, OpenAI API, pypdf
- **Extension:** Chrome Manifest V3, vanilla JS/CSS

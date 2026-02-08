import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    IngestResponse,
    HealthResponse,
)
from app.services.pdf_processor import extract_text_from_pdf
from app.services.vector_store import VectorStore
from app.services.rag_service import RAGService
from app.services.question_logger import QuestionLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global service instances
vector_store: VectorStore | None = None
rag_service: RAGService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, clean up on shutdown."""
    global vector_store, rag_service
    logger.info("Starting up services...")
    vector_store = VectorStore()
    rag_service = RAGService(vector_store)
    logger.info("Services initialized successfully.")
    yield
    logger.info("Shutting down services.")


app = FastAPI(
    title="Nexzoneo Support Chatbot API",
    description="AI-powered support chatbot for Nexzoneo digital banking.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _verify_admin(authorization: str | None) -> None:
    """Verify admin authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required.")
    # Expect: "Bearer <admin_secret>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != settings.ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin credentials.")


@app.post("/ingest", response_model=IngestResponse)
async def ingest_pdfs(
    files: list[UploadFile] = File(...),
    authorization: str | None = Header(default=None),
):
    """[ADMIN ONLY] Upload and ingest PDF files into the knowledge base."""
    _verify_admin(authorization)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    total_chunks = 0
    files_processed = 0

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            logger.warning(f"Skipping non-PDF file: {file.filename}")
            continue

        try:
            pdf_bytes = await file.read()
            chunks = extract_text_from_pdf(pdf_bytes, file.filename)

            if chunks:
                added = vector_store.add_documents(chunks)
                total_chunks += added
                files_processed += 1
                logger.info(f"Ingested '{file.filename}': {added} chunks")
            else:
                logger.warning(f"No text extracted from '{file.filename}'")
        except Exception as e:
            logger.error(f"Error processing '{file.filename}': {e}")
            continue

    if files_processed == 0:
        raise HTTPException(
            status_code=400,
            detail="No valid PDF files could be processed.",
        )

    return IngestResponse(
        message=f"Successfully processed {files_processed} PDF file(s).",
        files_processed=files_processed,
        total_chunks=total_chunks,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Ask a question about Nexzoneo products, policies, and services."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    response = rag_service.chat(request.question, history=request.history)
    return response


@app.post("/clear")
async def clear_knowledge_base(authorization: str | None = Header(default=None)):
    """[ADMIN ONLY] Clear all documents from the knowledge base."""
    _verify_admin(authorization)
    vector_store.clear()
    logger.info("Knowledge base cleared by admin.")
    return {"message": "Knowledge base cleared successfully."}


@app.get("/logs")
async def get_unanswered_logs(
    authorization: str | None = Header(default=None),
    limit: int = 50,
):
    """[ADMIN ONLY] Get recent unanswered questions log."""
    _verify_admin(authorization)
    logs = QuestionLogger.get_recent_logs(limit=limit)
    return {
        "total": len(logs),
        "logs": logs,
    }


@app.get("/documents")
async def list_documents(authorization: str | None = Header(default=None)):
    """[ADMIN ONLY] List all uploaded PDFs in the knowledge base."""
    _verify_admin(authorization)
    docs = vector_store.list_documents() if vector_store else []
    return {"documents": docs}


@app.get("/stats")
async def get_stats(authorization: str | None = Header(default=None)):
    """[ADMIN ONLY] Get chatbot statistics."""
    _verify_admin(authorization)
    doc_count = vector_store.document_count if vector_store else 0
    logs = QuestionLogger.get_recent_logs(limit=9999)
    total_unanswered = len(logs)
    reasons = {}
    for log in logs:
        r = log.get("reason", "unknown")
        if r.startswith("llm_error"):
            r = "llm_error"
        reasons[r] = reasons.get(r, 0) + 1
    return {
        "document_count": doc_count,
        "total_unanswered": total_unanswered,
        "unanswered_by_reason": reasons,
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check the health of the service and return document count."""
    doc_count = vector_store.document_count if vector_store else 0
    return HealthResponse(
        status="healthy",
        document_count=doc_count,
    )


# Serve admin dashboard
ADMIN_DIR = Path(__file__).resolve().parent.parent / "admin"
if ADMIN_DIR.exists():
    @app.get("/admin")
    async def admin_dashboard():
        return FileResponse(ADMIN_DIR / "index.html")

    app.mount("/admin-static", StaticFiles(directory=str(ADMIN_DIR)), name="admin-static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )

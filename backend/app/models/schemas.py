from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class Citation(BaseModel):
    pdf_name: str
    page: int
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []


class IngestResponse(BaseModel):
    message: str
    files_processed: int
    total_chunks: int


class HealthResponse(BaseModel):
    status: str
    document_count: int

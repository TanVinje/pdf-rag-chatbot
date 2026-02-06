import logging
from openai import OpenAI

from app.config import settings
from app.models.schemas import ChatResponse, Citation
from app.services.vector_store import VectorStore, QueryResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions ONLY based on the provided document context. Follow these rules strictly:

1. Only use information from the provided context to answer questions.
2. If the context does not contain enough information to answer the question, say "I couldn't find relevant information in the uploaded documents."
3. Always cite which document and page the information comes from using the format [Source: filename, Page X].
4. Be concise and accurate in your answers.
5. Do not make up or infer information that is not explicitly stated in the context.
6. If multiple documents contain relevant information, synthesize the answer and cite all sources."""


def _build_context(results: list[QueryResult]) -> str:
    """Build a context string from query results for the LLM prompt."""
    context_parts: list[str] = []
    for i, result in enumerate(results, start=1):
        context_parts.append(
            f"[Document {i}: {result.pdf_name}, Page {result.page_number}]\n"
            f"{result.text}\n"
        )
    return "\n---\n".join(context_parts)


def _extract_citations(results: list[QueryResult]) -> list[Citation]:
    """Extract and deduplicate citations from query results."""
    seen: set[tuple[str, int]] = set()
    citations: list[Citation] = []

    for result in results:
        key = (result.pdf_name, result.page_number)
        if key not in seen:
            seen.add(key)
            # Use the first ~200 characters as a snippet
            snippet = result.text[:200].strip()
            if len(result.text) > 200:
                snippet += "..."
            citations.append(
                Citation(
                    pdf_name=result.pdf_name,
                    page=result.page_number,
                    snippet=snippet,
                )
            )

    return citations


def _create_llm_client() -> tuple[OpenAI, str]:
    """Create LLM client, preferring Ollama (free local) over OpenAI.

    Returns:
        Tuple of (OpenAI-compatible client, model name).
    """
    # Try Ollama first (free, local)
    try:
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # Ollama doesn't need a real key
        )
        # Quick check that Ollama is reachable
        client.models.list()
        logger.info("Using Ollama (local) for chat with model: llama3.2")
        return client, "llama3.2"
    except Exception:
        logger.info("Ollama not available, checking for OpenAI API key...")

    # Fall back to OpenAI
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.strip():
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(f"Using OpenAI for chat with model: {settings.OPENAI_CHAT_MODEL}")
        return client, settings.OPENAI_CHAT_MODEL

    return None, ""


class RAGService:
    """Retrieval-Augmented Generation service that ties together
    vector search and LLM calls."""

    def __init__(self, vector_store: VectorStore):
        self._vector_store = vector_store
        self._llm_client, self._model = _create_llm_client()
        if not self._llm_client:
            logger.warning("No LLM available. Install Ollama or set OPENAI_API_KEY.")

    def chat(self, question: str) -> ChatResponse:
        """Process a user question using RAG.

        1. Query the vector store for relevant chunks.
        2. Check if similarity threshold is met.
        3. Build context and call the LLM.
        4. Return answer with citations.

        Args:
            question: The user's question.

        Returns:
            ChatResponse with answer and citations.
        """
        if not self._llm_client:
            return ChatResponse(
                answer="No LLM available. Please install Ollama or configure an OpenAI API key.",
                citations=[],
            )

        # Step 1: Retrieve relevant chunks
        results = self._vector_store.query(question, top_k=settings.TOP_K)

        if not results:
            return ChatResponse(
                answer="No documents have been uploaded yet. Please upload PDF files first.",
                citations=[],
            )

        # Step 2: Check similarity threshold
        best_score = results[0].score
        logger.info(f"Best similarity score: {best_score:.4f} (threshold: {settings.SIMILARITY_THRESHOLD})")

        if best_score < settings.SIMILARITY_THRESHOLD:
            return ChatResponse(
                answer="I couldn't find relevant information in the uploaded documents to answer your question.",
                citations=[],
            )

        # Filter results above threshold
        relevant_results = [r for r in results if r.score >= settings.SIMILARITY_THRESHOLD]

        # Step 3: Build context and call LLM
        context = _build_context(relevant_results)
        user_message = (
            f"Context from uploaded documents:\n\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Please answer based only on the provided context. "
            f"Cite sources using [Source: filename, Page X] format."
        )

        try:
            response = self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            answer = response.choices[0].message.content or "No response generated."
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ChatResponse(
                answer=f"An error occurred while generating the answer: {str(e)}",
                citations=[],
            )

        # Step 4: Extract citations
        citations = _extract_citations(relevant_results)

        return ChatResponse(answer=answer, citations=citations)

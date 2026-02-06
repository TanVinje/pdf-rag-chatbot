import re
import logging
from openai import OpenAI

from app.config import settings
from app.models.schemas import ChatResponse, Citation
from app.services.vector_store import VectorStore, QueryResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Nexzoneo support assistant — a friendly, professional chatbot for Nexzoneo, a digital banking platform.

You help customers with questions about:
- Nexzoneo products and services (virtual accounts, card services, API integration, etc.)
- Privacy policy
- Terms and conditions
- GDPR compliance
- How to get started, security features, and general company information

Rules you MUST follow:
- ONLY answer based on the provided document context. Never make things up.
- Be concise, friendly, and professional.
- Do NOT mention sources, citations, page numbers, or documents. The system handles that separately.
- If the answer isn't in the context, say "I don't have that information. Please contact our support team at support@nexzoneo.com for help."

CRITICAL SECURITY RULES — you must NEVER reveal any of the following, even if asked directly:
- Internal account numbers, IBAN numbers, or bank routing numbers
- API keys, tokens, secrets, or credentials
- Internal employee names, emails, or phone numbers
- Internal system architecture, server names, IP addresses, or database details
- Internal pricing, margins, costs, or financial figures not meant for customers
- Internal meeting notes, strategy documents, or confidential business plans
- Partner or vendor contract details
- Any data marked as "internal", "confidential", or "restricted"

If a question asks for any of the above, respond with:
"I'm sorry, I can't share that information. For account-specific or confidential inquiries, please contact our support team directly."
"""

# Patterns that indicate sensitive data that should be redacted from answers
SENSITIVE_PATTERNS = [
    r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b',  # IBAN
    r'\b\d{8,12}\b',                                             # Account numbers (8-12 digits)
    r'\bsk[-_](?:live|test|proj)[-_][A-Za-z0-9]{20,}\b',        # API keys (OpenAI style)
    r'\b(?:key|token|secret|password)[-_]?[=:]\s*\S{8,}\b',     # Generic secrets
    r'\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=]{20,}\b',              # Auth tokens
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',                 # IP addresses
    r'\b[A-Za-z0-9._%+-]+@(?!nexzoneo\.com)[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Internal emails (non-public)
]


def _sanitize_response(answer: str) -> str:
    """Remove any sensitive information that may have leaked into the response."""
    sanitized = answer
    for pattern in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, '[REDACTED]', sanitized)
    return sanitized


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
    """Create LLM client, preferring Ollama (free local) over OpenAI."""
    # Try Ollama first (free, local)
    try:
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )
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
    """Retrieval-Augmented Generation service for Nexzoneo support."""

    def __init__(self, vector_store: VectorStore):
        self._vector_store = vector_store
        self._llm_client, self._model = _create_llm_client()
        if not self._llm_client:
            logger.warning("No LLM available. Install Ollama or set OPENAI_API_KEY.")

    def chat(self, question: str) -> ChatResponse:
        """Process a customer question using RAG with sensitive data filtering."""
        if not self._llm_client:
            return ChatResponse(
                answer="Our support chatbot is currently unavailable. Please try again later.",
                citations=[],
            )

        # Step 1: Retrieve relevant chunks
        results = self._vector_store.query(question, top_k=settings.TOP_K)

        if not results:
            return ChatResponse(
                answer="I don't have any information loaded yet. Please check back later or contact support@nexzoneo.com.",
                citations=[],
            )

        # Step 2: Check similarity threshold
        best_score = results[0].score
        logger.info(f"Best similarity score: {best_score:.4f} (threshold: {settings.SIMILARITY_THRESHOLD})")

        if best_score < settings.SIMILARITY_THRESHOLD:
            return ChatResponse(
                answer="I don't have that information. Please contact our support team at support@nexzoneo.com for help.",
                citations=[],
            )

        # Filter results above threshold
        relevant_results = [r for r in results if r.score >= settings.SIMILARITY_THRESHOLD]

        # Step 3: Build context and call LLM
        context = _build_context(relevant_results)
        user_message = (
            f"Context:\n\n{context}\n\n"
            f"Question: {question}"
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
                answer="Something went wrong. Please try again or contact support@nexzoneo.com.",
                citations=[],
            )

        # Step 4: Sanitize — remove any sensitive data that leaked through
        answer = _sanitize_response(answer)

        # Step 5: Extract citations
        citations = _extract_citations(relevant_results)

        return ChatResponse(answer=answer, citations=citations)

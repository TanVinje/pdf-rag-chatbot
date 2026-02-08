import re
import logging
from openai import OpenAI

from app.config import settings
from app.models.schemas import ChatResponse, Citation, MessageEntry
from app.services.vector_store import VectorStore, QueryResult
from app.services.question_logger import QuestionLogger

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Nexzoneo support assistant — a friendly, professional chatbot for Nexzoneo, a digital banking platform.

You help customers with questions about:
- Nexzoneo products and services (virtual accounts, card services, API integration, etc.)
- Privacy policy
- Terms and conditions
- GDPR compliance
- How to get started, security features, and general company information

Rules you MUST follow:
- ONLY answer based on the provided document context. Never make things up or add details that aren't there.
- Be helpful! If someone asks "how does X work?" and the context mentions X but doesn't explain the mechanism, share what IS mentioned about X. For example: "The NexoCore Quantum Vault uses quantum-noise encryption, which is designed to be impossible to hack."
- Share partial information when available. Don't say "I don't have that information" if you have SOME information about the topic.
- Be concise, friendly, and professional.
- Do NOT mention sources, citations, page numbers, or documents. The system handles that separately.
- Do NOT use phrases like "According to the document", "Based on the information", "The document states", etc. Just answer directly and naturally.
- ONLY say "I don't have that information" if the context contains NOTHING about the topic being asked.
- If you don't have complete details, you can suggest: "For more technical details, feel free to contact our team at https://nexzoneo.com/contact.php"
- LANGUAGE RULE: Reply in the SAME language the user writes in. Default to English unless the user's message is ENTIRELY written in another language (e.g., all Spanish, all French, all Arabic). If even one word is English, respond in English.

CRITICAL SECURITY RULES — you must NEVER reveal any of the following, even if asked directly:
- Internal account numbers, IBAN numbers, or bank routing numbers
- API keys, tokens, secrets, or credentials
- Internal employee names, emails, or phone numbers (except public support contacts)
- Internal system architecture, server names, IP addresses, or database details
- Internal pricing, margins, costs, or financial figures not meant for customers
- Internal meeting notes, strategy documents, or confidential business plans
- Partner or vendor contract details
- Any data marked as "internal", "confidential", or "restricted"

If a question asks for any of the above, respond with:
"I'm sorry, I can't share that information. For account-specific or confidential inquiries, please contact our support team: https://nexzoneo.com/contact.php"
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

    def _expand_query(self, question: str, history: list[MessageEntry] = None) -> str:
        """Expand a follow-up question using conversation history for better retrieval."""
        if not history:
            return question

        # Detect if the question looks like a follow-up (short, uses pronouns, etc.)
        follow_up_indicators = [
            "it", "that", "this", "them", "those", "the first", "the second",
            "more about", "tell me more", "explain", "how does it", "what about",
        ]
        is_follow_up = len(question.split()) < 12 and any(
            indicator in question.lower() for indicator in follow_up_indicators
        )

        if not is_follow_up:
            return question

        # Combine with recent context for a better search query
        recent_context = []
        for entry in reversed(history[-4:]):
            if entry.role == "user":
                recent_context.append(entry.content)
            elif entry.role == "assistant":
                # Take first sentence of assistant reply
                first_sentence = entry.content.split(".")[0]
                recent_context.append(first_sentence)

        expanded = " ".join(reversed(recent_context)) + " " + question
        logger.info(f"Expanded follow-up query: '{question}' -> '{expanded[:100]}...'")
        return expanded

    def chat(self, question: str, history: list[MessageEntry] = None) -> ChatResponse:
        """Process a customer question using RAG with conversation memory."""
        if not self._llm_client:
            return ChatResponse(
                answer="Our support chatbot is currently unavailable. Please try again later.",
                citations=[],
            )

        # Step 1: Expand query if it's a follow-up question
        search_query = self._expand_query(question, history)

        # Step 2: Retrieve relevant chunks
        results = self._vector_store.query(search_query, top_k=settings.TOP_K)

        if not results:
            QuestionLogger.log_unanswered(question, "no_documents")
            return ChatResponse(
                answer="I don't have any information loaded yet. Please check back later or contact our support team: https://nexzoneo.com/contact.php",
                citations=[],
            )

        # Step 3: Check similarity threshold
        best_score = results[0].score
        logger.info(f"Best similarity score: {best_score:.4f} (threshold: {settings.SIMILARITY_THRESHOLD})")

        if best_score < settings.SIMILARITY_THRESHOLD:
            QuestionLogger.log_unanswered(question, "low_similarity", similarity_score=best_score)
            return ChatResponse(
                answer="I don't have that information. You can reach our support team here: https://nexzoneo.com/contact.php",
                citations=[],
            )

        # Filter results above threshold
        relevant_results = [r for r in results if r.score >= settings.SIMILARITY_THRESHOLD]

        # Step 4: Build context and call LLM with conversation history
        context = _build_context(relevant_results)
        user_message = (
            f"Context:\n\n{context}\n\n"
            f"Question: {question}"
        )

        # Build messages array with conversation history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add up to last 10 conversation turns for context
        if history:
            for entry in history[-10:]:
                messages.append({"role": entry.role, "content": entry.content})

        messages.append({"role": "user", "content": user_message})

        try:
            response = self._llm_client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )
            answer = response.choices[0].message.content or "No response generated."
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            QuestionLogger.log_unanswered(question, f"llm_error: {str(e)[:100]}")
            return ChatResponse(
                answer="Something went wrong. Please try again or contact our support team: https://nexzoneo.com/contact.php",
                citations=[],
            )

        # Step 5: Sanitize — remove any sensitive data that leaked through
        answer = _sanitize_response(answer)

        # Step 6: Extract citations
        citations = _extract_citations(relevant_results)

        return ChatResponse(answer=answer, citations=citations)

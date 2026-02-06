import logging
from dataclasses import dataclass
from pypdf import PdfReader
from io import BytesIO

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """A chunk of text extracted from a PDF with metadata."""
    text: str
    pdf_name: str
    page_number: int
    chunk_id: int


def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 500) -> list[str]:
    """Split text into overlapping chunks.

    Args:
        text: The full text to chunk.
        chunk_size: Target size of each chunk in characters.
        overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        A list of text chunks.
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks


def extract_text_from_pdf(pdf_bytes: bytes, pdf_name: str) -> list[TextChunk]:
    """Extract text from a PDF file and split into chunks.

    Processes the PDF page by page, chunks each page's text,
    and attaches metadata (file name, page number, chunk id).

    Args:
        pdf_bytes: Raw bytes of the PDF file.
        pdf_name: Original filename of the PDF.

    Returns:
        A list of TextChunk objects with metadata.
    """
    all_chunks: list[TextChunk] = []
    chunk_counter = 0

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as e:
        logger.error(f"Failed to read PDF '{pdf_name}': {e}")
        return []

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Failed to extract text from page {page_num} of '{pdf_name}': {e}")
            continue

        if not page_text.strip():
            continue

        text_chunks = chunk_text(page_text)
        for chunk_text_str in text_chunks:
            all_chunks.append(
                TextChunk(
                    text=chunk_text_str,
                    pdf_name=pdf_name,
                    page_number=page_num,
                    chunk_id=chunk_counter,
                )
            )
            chunk_counter += 1

    logger.info(f"Extracted {chunk_counter} chunks from '{pdf_name}' ({len(reader.pages)} pages)")
    return all_chunks

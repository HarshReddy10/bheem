"""Document parsing utilities for knowledge base ingestion.

Supports: .txt, .md, .pdf, .docx
Includes text chunking with configurable overlap for RAG.
"""

from pathlib import Path
from typing import List

from app.utils.logger import logger


def load_text_file(file_path: Path) -> str:
    """Load a plain text or markdown file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def load_pdf_file(file_path: Path) -> str:
    """Load a PDF file and extract text from all pages."""
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(file_path))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except ImportError:
        logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
        return ""
    except Exception as e:
        logger.error(f"Error reading PDF {file_path}: {e}")
        return ""


def load_docx_file(file_path: Path) -> str:
    """Load a DOCX file and extract paragraph text."""
    try:
        from docx import Document

        doc = Document(str(file_path))
        text = "\n".join(
            para.text for para in doc.paragraphs if para.text.strip()
        )
        return text.strip()
    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        return ""
    except Exception as e:
        logger.error(f"Error reading DOCX {file_path}: {e}")
        return ""


def load_document(file_path: Path) -> str:
    """Load a document based on its file extension."""
    suffix = file_path.suffix.lower()
    loaders = {
        ".txt": load_text_file,
        ".md": load_text_file,
        ".pdf": load_pdf_file,
        ".docx": load_docx_file,
    }

    loader = loaders.get(suffix)
    if loader is None:
        logger.warning(f"Unsupported file type: {suffix} for {file_path}")
        return ""

    logger.info(f"Loading document: {file_path}")
    return loader(file_path)


def chunk_text(
    text: str, chunk_size: int = 500, chunk_overlap: int = 50
) -> List[str]:
    """Split text into overlapping chunks for vector storage.

    Uses paragraph boundaries for natural splits, with word-level
    fallback for paragraphs exceeding chunk_size.
    """
    if not text.strip():
        return []

    chunks: List[str] = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        # If paragraph fits in the current chunk, append it
        if len(current_chunk) + len(paragraph) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + paragraph
        else:
            # Save current chunk and start a new one with overlap
            if current_chunk:
                chunks.append(current_chunk)
                overlap_text = (
                    current_chunk[-chunk_overlap:] if chunk_overlap > 0 else ""
                )
                current_chunk = (
                    overlap_text + ("\n\n" if overlap_text else "") + paragraph
                )
            else:
                # Single paragraph exceeds chunk_size — split by words
                words = paragraph.split()
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= chunk_size:
                        current_chunk += (" " if current_chunk else "") + word
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                            overlap_text = (
                                current_chunk[-chunk_overlap:]
                                if chunk_overlap > 0
                                else ""
                            )
                            current_chunk = overlap_text + " " + word
                        else:
                            current_chunk = word

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def load_all_documents(directory: str) -> List[dict]:
    """Load all supported documents from a directory (recursive).

    Returns a list of dicts with keys: source, filename, content.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        logger.warning(f"Knowledge base directory not found: {directory}")
        return []

    supported_extensions = {".txt", ".md", ".pdf", ".docx"}
    documents: List[dict] = []

    for file_path in sorted(dir_path.rglob("*")):
        if file_path.suffix.lower() in supported_extensions:
            text = load_document(file_path)
            if text:
                documents.append(
                    {
                        "source": str(file_path),
                        "filename": file_path.name,
                        "content": text,
                    }
                )
                logger.info(f"Loaded: {file_path.name} ({len(text)} chars)")

    logger.info(f"Loaded {len(documents)} documents from {directory}")
    return documents

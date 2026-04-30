"""
One-time (and re-runnable) script to embed municipal PDF documents
into ChromaDB. Run whenever PDFs are added or updated.

Usage:
    python -m app.services.pdf_ingestor --pdf-dir ./municipal_docs
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import chromadb 
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

CHUNK_SIZE=800
CHUNK_OVERLAP=120

def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int=CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks"""
    chunks, start = [], 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end].strip())
        start+=size-overlap
    return [c for c in chunks if len(c)>60]

def _doc_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]

def ingest_pdfs(pdf_dir: Path) -> None:
    settings = get_settings()
    setup_logging()

    pdf_files = list(pdf_dir.glob("**/*.pdf"))
    if not pdf_files:
        logger.warning("no_pdfs_found", directory=str(pdf_dir))
        return 

    ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=settings.gemini_api_key,
        model_name="models/embedding-001"
    )

    client = chromadb.PersistentClient(path=settings.chroma_persist_path)
    collection = client.get_or_create_collection(
        name=settings.chroma_collection_name,
        embedding_function=ef,
        metadata={"hnsw:space":"cosine"}
    )

    for pdf_path in pdf_files:
        logger.info("ingesting_pdf", path=str(pdf_path))
        try:
            reader= PdfReader(str(pdf_path))
            full_text="\n".join(
                page.extract_text() or "" for page in reader.pages 
            )
        except Exception as exc:
            logger.error("pdf_read_failed", path=str(pdf_path), error=str(exc))
            continue

        chunks = _chunk_text(full_text)
        doc_hash = _doc_hash(full_text)
        ingested_at = datetime.now(timezone.utc).isoformat()

        ids, documents, metadatas = [], [], []
        for i, chunk in enumerate(chunks):
            chunk_id=f"{pdf_path.stem}_{doc_hash}_{i:04d}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "source":pdf_path.name,
                "doc_hash":doc_hash,
                "chunk_index":i,
                "ingested_at": ingested_at 
            })

        # Upsert
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(
            "pdf_ingested",
            source=pdf_path.name,
            chunks=len(chunks),
            doc_hash=doc_hash,
        )
    total=collection.count()
    logger.info("ingestion_complete", total_chunks=total)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", type=Path, default=Path("./municipal_docs"))
    args=parser.parse_args()
    ingest_pdfs(args.pdf_dir)
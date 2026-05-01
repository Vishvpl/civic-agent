import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import chromadb 
from chromadb.utils import embedding_functions
# Using unstructured for table-aware parsing
from unstructured.partition.pdf import partition_pdf

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

# Constants for narrative text chunking
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split regular narrative text into chunks."""
    chunks, start = [], 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end].strip())
        start += size - overlap
    return [c for c in chunks if len(c) > 60]

def _doc_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]

def ingest_pdfs(pdf_dir: Path) -> None:
    settings = get_settings()
    setup_logging()

    pdf_files = list(pdf_dir.glob("**/*.pdf"))
    if not pdf_files:
        logger.warning("no_pdfs_found", directory=str(pdf_dir))
        return 

    # 2026 Recommended Embedding Model for Gemini
    ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=settings.gemini_api_key,
        model_name="models/text-embedding-004" 
    )

    client = chromadb.PersistentClient(path=settings.chroma_persist_path)
    collection = client.get_or_create_collection(
        name=settings.chroma_collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

    for pdf_path in pdf_files:
        logger.info("processing_pdf_with_tables", path=str(pdf_path))
        try:
            # Use high-res strategy to identify and extract tables
            elements = partition_pdf(
                filename=str(pdf_path),
                infer_table_structure=True,
                chunking_strategy="by_title", # Keeps sections together
                max_characters=CHUNK_SIZE,
                new_after_n_chars=CHUNK_SIZE,
                combine_text_under_n_chars=CHUNK_OVERLAP,
                strategy="hi_res", # Necessary for table recognition
            )
        except Exception as exc:
            logger.error("unstructured_parse_failed", path=str(pdf_path), error=str(exc))
            continue

        ids, documents, metadatas = [], [], []
        ingested_at = datetime.now(timezone.utc).isoformat()
        
        # We process elements differently based on whether they are Tables or Text
        for i, element in enumerate(elements):
            element_type = element.category # 'Table', 'NarrativeText', 'Title', etc.
            
            # If it's a table, we use the HTML/Markdown representation
            if element_type == "Table":
                content = element.metadata.text_as_html or str(element)
                logger.debug("table_detected", source=pdf_path.name, index=i)
            else:
                content = str(element)

            if len(content) < 50: # Skip noise/empty lines
                continue

            doc_hash = _doc_hash(content)
            chunk_id = f"{pdf_path.stem}_{i:04d}_{doc_hash}"
            
            ids.append(chunk_id)
            documents.append(content)
            metadatas.append({
                "source": pdf_path.name,
                "element_type": element_type,
                "ingested_at": ingested_at,
                "is_table": element_type == "Table"
            })

        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("pdf_ingested", source=pdf_path.name, total_elements=len(ids))

    logger.info("ingestion_complete", total_chunks=collection.count())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", type=Path, default=Path("./municipal_docs"))
    args = parser.parse_args()
    ingest_pdfs(args.pdf_dir)
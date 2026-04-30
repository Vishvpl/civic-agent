"""
Provides a single shared ChromaDB collection instance.
Thread-safe for async use - ChromaDB's PersistentClient is synchronous, so we run queries in a threadpool executor.
"""

import asyncio
from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@lru_cache(maxsize=1)
def _get_collection():
    settings = get_settings()
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
    logger.info("chroma_collection_loaded", count=collection.count())
    return collection

async def query_collection(query_text: str, n_results: int) -> list[str]:
    """
    Async wrapper around ChromaDB's synchronous query.
    Returns a list of relevant document chunks.
    """

    loop=asyncio.get_running_loop()

    def _query():
        collection = _get_collection()
        results = collection.query(
            n_results=min(n_results,collection.count() or 1),
            include=["documents","metadatas","distances"]
        )
        docs=results.get("documents",[[]])[0]
        metas=results.get("metadatas",[[]])[0]
        distances=results.get("distances",[[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            logger.debug(
                "rag_chunk_retrieved",
                source=meta.get("source"),
                distance=round(dist,4),
                preview=doc[:80]
            )
        return docs
    return await loop.run_in_executor(None,_query)
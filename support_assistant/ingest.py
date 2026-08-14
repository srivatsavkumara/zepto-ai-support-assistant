"""
Ingestion + embedding module for the Zepto policy-assistant RAG pipeline.

Stage: ingestion -> embedding  (see README architecture section)

- load_documents(): reads docs/doc_*.txt off disk
- chunk_document(): one chunk per document (each doc is short and topically
  self-contained, so per-document chunking is the simplest correct scheme —
  explicitly allowed by the assignment spec)
- build_or_load_collection(): embeds each chunk with all-MiniLM-L6-v2 and
  upserts it into a persistent ChromaDB collection on disk (./chroma_db)
- retrieve_top_k(): embeds a query and returns the top-k most similar chunks
  by cosine similarity — this always runs for real (no MOCK_LLM branch here),
  since embeddings/ChromaDB need no API key and no network call at query time.
"""
import os
import glob
from typing import List, Dict

import chromadb
from sentence_transformers import SentenceTransformer

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
CHROMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "zepto_policies"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

_model = None


def get_embedder() -> SentenceTransformer:
    """Lazily load the local embedding model (downloaded once, cached by HF)."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def load_documents(docs_dir: str = DOCS_DIR) -> Dict[str, str]:
    """Read all docs/doc_*.txt files. Returns {doc_id: text}."""
    paths = sorted(glob.glob(os.path.join(docs_dir, "doc_*.txt")))
    if not paths:
        raise FileNotFoundError(
            f"No doc_*.txt files found in {docs_dir}. "
            "Did you run the corpus-creation cell in 01_ingest.ipynb?"
        )
    docs = {}
    for path in paths:
        doc_id = os.path.splitext(os.path.basename(path))[0]  # e.g. 'doc_01'
        with open(path, "r", encoding="utf-8") as f:
            docs[doc_id] = f.read().strip()
    return docs


def chunk_document(doc_id: str, text: str, max_chars: int = 400) -> List[Dict]:
    """
    Chunk a single document. Each source doc here is a single short policy
    paragraph (a few sentences), so we default to one chunk per document.
    If a document exceeds max_chars, fall back to a fixed-size split so the
    scheme still degrades gracefully on longer corpora.
    """
    if len(text) <= max_chars:
        return [{"chunk_id": f"{doc_id}_c0", "doc_id": doc_id, "text": text}]

    chunks = []
    for i, start in enumerate(range(0, len(text), max_chars)):
        piece = text[start:start + max_chars].strip()
        if piece:
            chunks.append({"chunk_id": f"{doc_id}_c{i}", "doc_id": doc_id, "text": piece})
    return chunks


def build_or_load_collection(persist_dir: str = CHROMA_DIR):
    """
    Embed every chunk from every document and upsert into a persistent
    ChromaDB collection. Safe to re-run: upsert is idempotent on chunk_id.
    """
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    docs = load_documents()
    all_chunks = []
    for doc_id, text in docs.items():
        all_chunks.extend(chunk_document(doc_id, text))

    embedder = get_embedder()
    texts = [c["text"] for c in all_chunks]
    embeddings = embedder.encode(texts, normalize_embeddings=True).tolist()

    collection.upsert(
        ids=[c["chunk_id"] for c in all_chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[{"doc_id": c["doc_id"]} for c in all_chunks],
    )
    return collection


def get_collection(persist_dir: str = CHROMA_DIR):
    """Get the collection, building it first if it doesn't exist yet."""
    client = chromadb.PersistentClient(path=persist_dir)
    try:
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() == 0:
            return build_or_load_collection(persist_dir)
        return collection
    except Exception:
        return build_or_load_collection(persist_dir)


def retrieve_top_k(query: str, k: int = 3, persist_dir: str = CHROMA_DIR) -> List[Dict]:
    """
    Embed `query` and return the top-k most similar chunks via cosine
    similarity search in ChromaDB. Always real (no mock branch) — see
    module docstring.
    """
    collection = get_collection(persist_dir)
    embedder = get_embedder()
    query_embedding = embedder.encode([query], normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
    )

    hits = []
    ids = results.get("ids", [[]])[0]
    docs_ = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0] if results.get("distances") else [None] * len(ids)

    for chunk_id, text, meta, dist in zip(ids, docs_, metas, dists):
        hits.append({
            "chunk_id": chunk_id,
            "doc_id": meta.get("doc_id"),
            "text": text,
            "distance": dist,
        })
    return hits


if __name__ == "__main__":
    build_or_load_collection()
    print("Collection built. Example query:")
    for h in retrieve_top_k("How long do I have to return a damaged item?", k=3):
        print(f"  [{h['chunk_id']}] dist={h['distance']:.4f}  {h['text'][:80]}...")

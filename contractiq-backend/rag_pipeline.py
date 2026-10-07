"""
Core RAG pipeline for ContractIQ (Python rebuild).

Flow:
  ingest_document(file_path, doc_id)
      -> load file (PyPDFLoader / Docx2txtLoader / TextLoader)
      -> split into chunks (RecursiveCharacterTextSplitter)
      -> embed each chunk (HuggingFaceEmbeddings, runs locally, free)
      -> store in a persisted Chroma collection keyed by doc_id

  get_answer(doc_id, question, history)
      -> embed the question
      -> similarity search against that doc's Chroma collection (top-k chunks)
      -> build a grounded prompt from the retrieved chunks
      -> call Groq (LLaMA 3.1 8B) for the final answer

This replaces the old TypeScript keyword-density chunk scoring and keyword-match
"RAG" (in huggingface.ts / groq.ts) with real semantic chunking + real vector
similarity search — same idea, done with actual embeddings instead of word counts.
"""

import os
import shutil

from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq

CHROMA_DIR = "chroma_db"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # free, runs locally, ONNX-optimized for low memory
GROQ_MODEL = "openai/gpt-oss-20b"

# ── Lazy singletons so the embedding model & LLM client are only created once ──

_embeddings = None


def get_embeddings() -> FastEmbedEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL, threads=1)
    return _embeddings


_llm = None


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")
        _llm = ChatGroq(model=GROQ_MODEL, temperature=0.3, api_key=api_key, request_timeout=60, max_retries=2)
    return _llm


# ── Loading & chunking ──

def _load_document(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
    elif ext in (".txt", ".md"):
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file extension: {ext}")
    return loader.load()


def ingest_document(file_path: str, doc_id: str) -> int:
    """Parse, chunk, embed, and persist a document under a Chroma collection
    named after doc_id. Returns the number of chunks stored."""
    docs = _load_document(file_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    if not chunks:
        raise ValueError("No extractable text found in document.")

    persist_dir = os.path.join(CHROMA_DIR, doc_id)
    vectorstore = Chroma(
        collection_name=doc_id,
        embedding_function=get_embeddings(),
        persist_directory=persist_dir,
    )
    vectorstore.add_documents(chunks)
    return len(chunks)


def _get_vectorstore(doc_id: str) -> Chroma:
    persist_dir = os.path.join(CHROMA_DIR, doc_id)
    if not os.path.isdir(persist_dir):
        raise ValueError(f"No document found for doc_id='{doc_id}'. Upload it first.")
    return Chroma(
        collection_name=doc_id,
        embedding_function=get_embeddings(),
        persist_directory=persist_dir,
    )


def delete_document(doc_id: str) -> None:
    persist_dir = os.path.join(CHROMA_DIR, doc_id)
    if os.path.isdir(persist_dir):
        try:
            vectorstore = Chroma(
                collection_name=doc_id,
                embedding_function=get_embeddings(),
                persist_directory=persist_dir,
            )
            vectorstore.delete_collection()
        finally:
            shutil.rmtree(persist_dir, ignore_errors=True)


# ── Retrieval + generation ──

SYSTEM_PROMPT = """You are a legal document analyst. Answer the user's question using \
ONLY the contract excerpts provided below.

Rules:
- Use plain, simple language — no legalese
- When relevant, mention which excerpt you're referencing (e.g. "Excerpt 2 says...")
- If asked what happens if someone does X, explain the consequences clearly
- If asked who benefits, compare both parties fairly
- Flag any unfair, one-sided, or risky clauses when relevant
- If the excerpts don't cover something, say so clearly rather than guessing

--- CONTRACT EXCERPTS ---
{context}
--- END EXCERPTS ---"""


def get_answer(doc_id: str, question: str, history: list | None = None, k: int = 4) -> dict:
    """Embed the question, retrieve the top-k most similar chunks from this
    document's vector store, and ask Groq to answer grounded in them."""
    history = history or []
    vectorstore = _get_vectorstore(doc_id)

    # similarity_search_with_score returns (Document, distance) pairs.
    # Chroma's default distance is cosine distance, so smaller = more similar;
    # we convert to an approximate 0-1 "relevance" score for display purposes only.
    results = vectorstore.similarity_search_with_score(question, k=k)

    context = "\n\n---\n\n".join(
        f"[Excerpt {i + 1}] {doc.page_content}" for i, (doc, _score) in enumerate(results)
    )
    sources = [
        {
            "excerpt": i + 1,
            "preview": doc.page_content[:200],
            "relevance_score": round(max(0.0, 1 - score), 3),
        }
        for i, (doc, score) in enumerate(results)
    ]

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
    for msg in history[-6:]:
        role = msg.get("role", "user")
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": question})

    response = get_llm().invoke(messages)

    return {"answer": response.content, "sources": sources}


def analyze_benefits(doc_id: str) -> str:
    """Analyze benefits and obligations in a single LLM call to avoid rate limits."""
    vectorstore = _get_vectorstore(doc_id)
    
    # Retrieve top 5 most relevant chunks to benefits and obligations
    query = "benefits obligations rights liabilities penalties"
    results = vectorstore.similarity_search(query, k=5)
    
    if not results:
        return "[]"
    
    # Combine all chunks into one prompt for a single LLM call
    combined_chunks = "\n\n---\n\n".join(
        f"[Section {i+1}]\n{doc.page_content}" for i, doc in enumerate(results)
    )
    
    SINGLE_PASS_PROMPT = f"""Analyze the following contract sections and extract ALL benefits, obligations, and key clauses for EACH party involved.

--- CONTRACT SECTIONS ---
{combined_chunks}
--- END SECTIONS ---

Produce a JSON array with the following format (and nothing else before or after the JSON):
[
  {{"party": "Party A (use actual name from document)", "benefit": "Brief benefit description", "clause": "The exact clause text or section reference", "score": 8}},
  {{"party": "Party B (use actual name from document)", "benefit": "Brief benefit description", "clause": "The exact clause text or section reference", "score": 7}}
]

Rules:
- Include 3-5 benefits per party
- Use actual party names from the document
- Score should be 1-10 indicating significance
- Each item MUST use the exact key "benefit" for the description field
- Ensure the JSON is valid and parseable"""

    llm = get_llm()
    messages = [
        {"role": "system", "content": "You are a legal contract analyst. Produce only valid JSON output."},
        {"role": "user", "content": SINGLE_PASS_PROMPT}
    ]
    
    response = llm.invoke(messages)
    return response.content


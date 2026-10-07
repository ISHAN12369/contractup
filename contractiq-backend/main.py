"""
ContractIQ — Python/LangChain backend (core RAG pipeline).

Endpoints:
  POST   /upload           -> parse + chunk + embed a document, returns doc_id
  POST   /chat             -> ask a question about a previously uploaded doc_id
  DELETE /document/{doc_id} -> remove a document's vector store
  GET    /health           -> liveness check

Run:
  uvicorn main:app --reload --port 8000

The existing Next.js frontend can call this instead of its own /api/extract and
/api/chat routes (CORS is enabled for http://localhost:3000).
"""

import os
import shutil
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_pipeline import delete_document, get_answer, ingest_document, analyze_benefits

load_dotenv()

app = FastAPI(title="ContractIQ RAG Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ChatRequest(BaseModel):
    doc_id: str
    question: str
    history: list[dict] = []


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Unsupported file type. Use PDF, DOCX, TXT, or MD.")

    doc_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        num_chunks = ingest_document(save_path, doc_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {e}")
    finally:
        if os.path.exists(save_path):
            os.remove(save_path)

    return {"doc_id": doc_id, "filename": file.filename, "num_chunks": num_chunks}


@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    try:
        return get_answer(req.doc_id, req.question, req.history)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


class BenefitsRequest(BaseModel):
    doc_id: str


@app.post("/benefits")
async def benefits(req: BenefitsRequest):
    try:
        result = analyze_benefits(req.doc_id)
        return {"answer": result}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/document/{doc_id}")
async def remove_document(doc_id: str):
    delete_document(doc_id)
    return {"deleted": doc_id}


@app.get("/health")
async def health():
    return {"status": "ok"}

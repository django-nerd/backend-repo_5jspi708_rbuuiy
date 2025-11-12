import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
import requests
from bs4 import BeautifulSoup
from database import create_document, get_documents

app = FastAPI(title="AI Docs Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    tags: Optional[List[str]] = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = 3


@app.get("/")
def read_root():
    return {"message": "AI Docs Chatbot Backend is running"}


@app.post("/api/ingest")
def ingest_resource(payload: IngestRequest):
    try:
        resp = requests.get(str(payload.url), timeout=10)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    # Basic content extraction using BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove script and style tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())

    title = payload.title or (soup.title.string.strip() if soup.title and soup.title.string else str(payload.url))

    doc = {
        "title": title,
        "url": str(payload.url),
        "content": text,
        "tags": payload.tags or [],
    }

    try:
        doc_id = create_document("resource", doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {"status": "ok", "id": doc_id, "title": title, "length": len(text)}


@app.get("/api/resources")
def list_resources(tag: Optional[str] = None, limit: int = 20):
    try:
        filt = {"tags": {"$in": [tag]}} if tag else {}
        items = get_documents("resource", filt, limit)
        # Convert ObjectId and datetime fields to strings for JSON serialization
        from bson import ObjectId
        from datetime import datetime
        def normalize(d):
            out = {}
            for k, v in d.items():
                if isinstance(v, ObjectId):
                    out[k] = str(v)
                elif isinstance(v, datetime):
                    out[k] = v.isoformat()
                else:
                    out[k] = v
            return out
        return [normalize(i) for i in items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.post("/api/ask")
def ask_question(payload: AskRequest):
    # Very simple retrieval: keyword overlap + cosine-like scoring on term frequency
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    try:
        # Fetch a reasonable number of docs
        docs = get_documents("resource", {}, 100)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not docs:
        return {"answer": "I don't have any resources yet. Please add a website or docs first.", "sources": []}

    import math
    import re
    from collections import Counter

    def tokenize(t: str):
        return [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", t)]

    q_tokens = tokenize(question)
    q_counts = Counter(q_tokens)

    # Compute simple TF score per doc on query terms, then select top_k
    scored = []
    for d in docs:
        content = d.get("content", "")
        tokens = tokenize(content)
        if not tokens:
            continue
        counts = Counter(tokens)
        score = sum(counts[t] for t in q_tokens)
        if score > 0:
            scored.append((score, d))

    if not scored:
        return {"answer": "I couldn't find information about that in the provided resources.", "sources": []}

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [d for _, d in scored[: payload.top_k]]

    # Compose a concise extract answer by pulling the most relevant sentences containing query terms
    def extract_snippets(text: str, q_terms: List[str], max_chars: int = 600):
        sentences = re.split(r"(?<=[.!?])\s+", text)
        selected = []
        for s in sentences:
            s_low = s.lower()
            if any(t in s_low for t in q_terms):
                selected.append(s.strip())
            if sum(len(x) for x in selected) > max_chars:
                break
        if selected:
            return " ".join(selected)[:max_chars]
        return text[:max_chars]

    snippets = [extract_snippets(d.get("content", ""), q_tokens) for d in top]
    combined = " \n\n".join(snippets)

    # Formulate a helpful answer summary
    answer = (
        "Here's what I found based on your resources: \n\n" + combined +
        "\n\nIf you'd like, you can add more sources for better answers."
    )

    # Prepare sources metadata
    def normalize_source(d):
        from bson import ObjectId
        from datetime import datetime
        out = {}
        for k, v in d.items():
            if isinstance(v, ObjectId):
                out[k] = str(v)
            elif isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        # keep only small subset
        return {"id": out.get("_id"), "title": out.get("title"), "url": out.get("url")}

    sources = [normalize_source(d) for d in top]

    return {"answer": answer, "sources": sources}


@app.get("/test")
def test_database():
    # Reuse original diagnostics
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

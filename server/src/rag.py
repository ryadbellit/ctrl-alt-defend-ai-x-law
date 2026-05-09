import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv

from google import genai
from google.genai import types
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

load_dotenv()

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3-flash-preview"

router = APIRouter()


# -------------------------------------------------------
# Store Management
# -------------------------------------------------------

def create_store(display_name: str) -> str:
    """
    Create a new File Search Store.
    Call this ONCE when setting up the project — save the returned
    store name in your .env as FILE_SEARCH_STORE_NAME.
    """
    store = client.file_search_stores.create(
        config={"display_name": display_name}
    )
    print(f"Store created: {store.name}")
    return store.name


def get_store_name() -> str:
    store_name = os.environ.get("FILE_SEARCH_STORE_NAME")
    if not store_name:
        raise ValueError("FILE_SEARCH_STORE_NAME is not set in your .env file.")
    return store_name


# -------------------------------------------------------
# Ingestion
# -------------------------------------------------------

def ingest_document(file_path: str, metadata: dict = {}) -> None:
    """
    Upload and index a legal document (PDF, TXT, DOCX) into the File Search Store.
    """
    store_name = get_store_name()
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"Ingesting {path.name} into store {store_name}...")

    custom_metadata = [
        {"key": k, "string_value": str(v)} for k, v in metadata.items()
    ]

    operation = client.file_search_stores.upload_to_file_search_store(
        file=str(path),
        file_search_store_name=store_name,
        config={
            "display_name": path.name,
            "custom_metadata": custom_metadata
        }
    )

    # Poll avec timeout
    intervals = [2, 2, 2, 5, 5, 5, 10, 10, 10, 15]
    for i, wait in enumerate(intervals):
        operation = client.operations.get(operation)
        if operation.done:
            print(f"Done: {path.name} indexed in ~{sum(intervals[:i])}s")
            return
        print(f"Indexing... ({wait}s)")
        time.sleep(wait)

    print("Warning: indexing timed out — file may still be processing in the background.")


def ingest_folder(folder_path: str, metadata: dict = {}) -> None:
    folder = Path(folder_path)
    supported = {".pdf", ".txt", ".docx", ".md"}
    files = [f for f in folder.iterdir() if f.suffix.lower() in supported]

    if not files:
        print(f"No supported files found in {folder_path}")
        return

    for file in files:
        try:
            ingest_document(str(file), metadata)
        except Exception as e:
            print(f"Failed to ingest {file.name}: {e}")

    print(f"\nIngestion complete: {len(files)} files processed.")


# -------------------------------------------------------
# Core RAG function (used by both /chat and /rag/suggest)
# -------------------------------------------------------

def query_rag(user_message: str, history: list[types.Content] = []) -> dict:
    """
    Send a message to Gemini with File Search enabled on every call.
    Supports multi-turn conversation via history.
    Returns { "reply": str, "sources": list[str] }
    """
    store_name = get_store_name()

    system_prompt = """
    You are a legal mediator assistant for Quebec small claims and civil rights court.

    INSTRUCTIONS:
    - Always search the documents for similar past cases before answering
    - Base your answer on the retrieved documents when possible
    - At the END of your response, add a section called "SOURCES:"
    - In that section, list the exact display_name of every document you used
    - Format: SOURCES: [document1.txt, document2.txt]
    - If no document was found, write SOURCES: []
    - NEVER invent or hallucinate case references
    - Only cite cases that exist in the provided documents
    """

    # System prompt + conversation history + new user message
    contents = [
        types.Content(role="user", parts=[types.Part(text=system_prompt)]),
        types.Content(role="model", parts=[types.Part(text="Compris. Je suis prêt à vous aider.")]),
        *history,
        types.Content(role="user", parts=[types.Part(text=user_message)])
    ]

    # Retry automatique si rate limit
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[
                        types.Tool(
                            file_search=types.FileSearch(
                                file_search_store_names=[store_name]
                            )
                        )
                    ]
                )
            )
            break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = (attempt + 1) * 30
                print(f"Rate limit. Waiting {wait}s...")
                time.sleep(wait)
            else:
                raise

    # Extract sources from the response text
    text = response.text
    sources = []

    match = re.search(r'SOURCES:\s*\[([^\]]*)\]', text)
    if match:
        raw = match.group(1).strip()
        if raw:
            sources = [s.strip() for s in raw.split(",")]
        text = text[:match.start()].strip()

    return {"reply": text, "sources": sources}


# -------------------------------------------------------
# Pydantic Models
# -------------------------------------------------------

class Message(BaseModel):
    role: str       # "user" or "model"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []

class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []

class CaseQuery(BaseModel):
    case_description: str

class IngestRequest(BaseModel):
    file_path: str
    metadata: dict = {}


# -------------------------------------------------------
# FastAPI Routes
# -------------------------------------------------------

def build_gemini_history(history: list[Message]) -> list[types.Content]:
    return [
        types.Content(
            role=msg.role,
            parts=[types.Part(text=msg.content)]
        )
        for msg in history
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint — every message triggers a RAG search.
    Supports multi-turn conversation via history.
    """
    try:
        gemini_history = build_gemini_history(request.history)
        result = query_rag(request.message, gemini_history)
        return ChatResponse(reply=result["reply"], sources=result["sources"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/suggest")
def suggest_resolution(body: CaseQuery):
    """
    One-shot resolution suggestion based on past cases.
    """
    try:
        result = query_rag(body.case_description)
        return {"suggestion": result["reply"], "sources": result["sources"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/ingest")
def ingest(body: IngestRequest):
    """
    Ingest a single document into the RAG store.
    """
    try:
        ingest_document(body.file_path, body.metadata)
        return {"status": "ok", "file": body.file_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------
# Local test
# -------------------------------------------------------

if __name__ == "__main__":
    result = query_rag("Quel est le montant exact de la pénalité dans le cas ZEBRA-9999?")
    print("Reply:", result["reply"])
    print("Sources:", result["sources"])
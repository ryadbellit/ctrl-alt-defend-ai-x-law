import os
import google.generativeai as genai
from google.generativeai import types
from pathlib import Path

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-1.5-pro"


# -------------------------------------------------------
# Store Management
# -------------------------------------------------------

def create_store(display_name: str) -> str:
    """
    Create a new File Search Store.
    Call this ONCE when setting up the project — save the returned
    store name in your .env as FILE_SEARCH_STORE_NAME.

    Returns the store resource name (e.g. 'fileSearchStores/abc-123').
    """
    store = genai.create_file_search_store(display_name=display_name)
    print(f"Store created: {store.name}")
    return store.name


def get_store_name() -> str:
    """
    Returns the store name from the environment.
    Make sure FILE_SEARCH_STORE_NAME is set in your .env file.
    """
    store_name = os.environ.get("FILE_SEARCH_STORE_NAME")
    if not store_name:
        raise ValueError(
            "FILE_SEARCH_STORE_NAME is not set. "
            "Run create_store() once and save the result to your .env file."
        )
    return store_name


# -------------------------------------------------------
# Ingestion
# -------------------------------------------------------

def ingest_document(file_path: str, metadata: dict = {}) -> None:
    """
    Upload and index a legal document (PDF, TXT, DOCX) into the File Search Store.
    This is called by the Celery worker when a new case document is uploaded.

    Args:
        file_path: Local path to the file (e.g. '/tmp/jugement_2023.pdf')
        metadata:  Optional key/value pairs for filtering later
                   e.g. {"type": "jugement", "year": "2023", "province": "QC"}
    """
    store_name = get_store_name()
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"Ingesting {path.name} into store {store_name}...")

    genai.upload_to_file_search_store(
        file_search_store=store_name,
        path=str(path),
        metadata=metadata,
    )

    print(f"Done: {path.name} indexed successfully.")


def ingest_folder(folder_path: str, metadata: dict = {}) -> None:
    """
    Ingest all PDFs and text files in a folder.
    Useful for the non-coder teammate to bulk-upload legal cases.

    Args:
        folder_path: Path to folder containing legal documents
        metadata:    Shared metadata applied to all files in the folder
    """
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
# Retrieval & Suggestions
# -------------------------------------------------------

def get_resolution_suggestion(case_description: str) -> dict:
    """
    Given a description of a dispute, retrieve similar past cases
    and return a resolution suggestion with cited sources.

    Args:
        case_description: Free-text description of the current dispute

    Returns:
        {
            "suggestion": "...",   # AI-generated resolution suggestion
            "sources": [...]       # List of cited document names
        }
    """
    store_name = get_store_name()
    model = genai.GenerativeModel(MODEL)

    prompt = f"""
    You are a legal mediator assistant specializing in small claims and civil rights cases in Quebec, Canada.

    Based on the following dispute, analyze similar past cases and suggest a fair resolution.
    Always cite the specific past cases that inform your suggestion.
    Be concise, neutral, and focus on what a mediator would recommend.

    Dispute description:
    {case_description}
    """

    response = model.generate_content(
        prompt,
        tools=[
            types.Tool(
                file_search=types.FileSearchTool(
                    file_search_store_names=[store_name]
                )
            )
        ]
    )

    # Extract cited sources from the response metadata
    sources = []
    if hasattr(response, "candidates"):
        for candidate in response.candidates:
            if hasattr(candidate, "grounding_metadata"):
                for chunk in candidate.grounding_metadata.grounding_chunks:
                    if hasattr(chunk, "retrieved_context"):
                        sources.append(chunk.retrieved_context.title)

    return {
        "suggestion": response.text,
        "sources": list(set(sources))  # deduplicate
    }


def get_relevant_laws(case_description: str) -> str:
    """
    Retrieve relevant laws and articles applicable to the dispute.
    Useful to surface to both parties during mediation.
    """
    store_name = get_store_name()
    model = genai.GenerativeModel(MODEL)

    prompt = f"""
    You are a legal research assistant for Quebec small claims court.
    Given the following dispute, identify the most relevant laws,
    articles, and legal precedents that apply. Be specific and cite sources.

    Dispute:
    {case_description}
    """

    response = model.generate_content(
        prompt,
        tools=[
            types.Tool(
                file_search=types.FileSearchTool(
                    file_search_store_names=[store_name]
                )
            )
        ]
    )

    return response.text


# -------------------------------------------------------
# FastAPI Route (import this in your routes/rag.py)
# -------------------------------------------------------

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/rag", tags=["RAG"])


class CaseQuery(BaseModel):
    case_description: str


@router.post("/suggest")
def suggest_resolution(body: CaseQuery):
    """
    Called when both parties request an AI-assisted resolution suggestion.
    """
    try:
        result = get_resolution_suggestion(body.case_description)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/laws")
def relevant_laws(body: CaseQuery):
    """
    Returns relevant laws and articles for the current dispute.
    """
    try:
        result = get_relevant_laws(body.case_description)
        return {"laws": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest")
def ingest(file_path: str, metadata: dict = {}):
    """
    Ingest a single document into the RAG store.
    In production, this should be called by the Celery worker, not directly.
    """
    try:
        ingest_document(file_path, metadata)
        return {"status": "ok", "file": file_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
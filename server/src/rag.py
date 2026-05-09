import os
from google import genai
from google.genai import types
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads the .env at project root

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------

# New SDK uses a Client object, not genai.configure()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3-flash-preview"


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
    store = client.file_search_stores.create(
        config={"display_name": display_name}
    )
    print(f"Store created: {store.name}")
    return store.name


def get_store_name() -> str:
    """
    Returns the store name from the environment.
    Make sure FILE_SEARCH_STORE_NAME is set in your .env file.
    """
    store_name = os.environ.get("FILE_SEARCH_STORE_NAME")
    return store_name


# -------------------------------------------------------
# Ingestion
# -------------------------------------------------------

import time

def ingest_document(file_path: str, metadata: dict = {}) -> None:
    """
    Upload and index a legal document (PDF, TXT, DOCX) into the File Search Store.

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

    # Build custom metadata list from dict
    custom_metadata = [
        {"key": k, "string_value": str(v)} for k, v in metadata.items()
    ]

    # Upload and index the file (returns a Long Running Operation)
    operation = client.file_search_stores.upload_to_file_search_store(
        file=str(path),
        file_search_store_name=store_name,
        config={
            "display_name": path.name,
            "custom_metadata": custom_metadata
        }
    )

    # Wait for indexing to complete before returning
    while not operation.done:
        print("Indexing in progress...")
        time.sleep(5)
        operation = client.operations.get(operation)

    print(f"Done: {path.name} indexed successfully.")


def ingest_folder(folder_path: str, metadata: dict = {}) -> None:
    """
    Ingest all PDFs and text files in a folder.
    Useful for the non-coder teammate to bulk-upload legal cases.
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
    store_name = get_store_name()

    prompt = f"""
    You are a legal mediator for Quebec small claims court.

    INSTRUCTIONS:
    - Search the documents for similar past cases
    - At the END of your response, add a section called "SOURCES:" 
    - In that section, list the exact display_name of every document you used
    - Format: SOURCES: [document1.txt, document2.txt]
    - If no document was found, write SOURCES: []

    Dispute: {case_description}
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
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

    # Extraire les sources depuis le texte de la réponse
    import re
    text = response.text
    sources = []

    match = re.search(r'SOURCES:\s*\[([^\]]*)\]', text)
    if match:
        raw = match.group(1).strip()
        if raw:
            sources = [s.strip() for s in raw.split(",")]
        # Nettoyer le texte pour ne pas afficher la ligne SOURCES
        text = text[:match.start()].strip()

    return {
        "suggestion": text,
        "sources": sources
    }

def get_relevant_laws(case_description: str) -> str:
    """
    Retrieve relevant laws and articles applicable to the dispute.
    """
    store_name = get_store_name()

    prompt = f"""
    You are a legal mediator for Quebec small claims court.
    STRICT RULES:
    - ONLY cite cases that exist verbatim in the provided documents
    - If no relevant case exists in the documents, say "Aucun cas similaire trouvé dans la base de données"
    - NEVER invent or hallucinate case references
    - Always mention the exact case number from the document

    Dispute: {case_description}
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
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

    return response.text


# -------------------------------------------------------
# FastAPI Routes (import this in your routes/rag.py)
# -------------------------------------------------------

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/rag", tags=["RAG"])


class CaseQuery(BaseModel):
    case_description: str


@router.post("/suggest")
def suggest_resolution(body: CaseQuery):
    try:
        result = get_resolution_suggestion(body.case_description)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/laws")
def relevant_laws(body: CaseQuery):
    try:
        result = get_relevant_laws(body.case_description)
        return {"laws": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest")
def ingest(file_path: str, metadata: dict = {}):
    try:
        ingest_document(file_path, metadata)
        return {"status": "ok", "file": file_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------
# Run this ONCE to create your store, then delete it
# -------------------------------------------------------

if __name__ == "__main__":
    result = get_resolution_suggestion(
        "Quel est le montant exact de la pénalité dans le cas ZEBRA-9999?"
    )
    print(result["suggestion"])
    print("Suggestion:", result["suggestion"])
    print("Sources:", result["sources"])
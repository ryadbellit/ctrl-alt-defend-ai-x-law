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

_client = None
MODEL = "gemini-3-flash-preview"

def get_client():
    """Lazy initialization of Gemini client to avoid crash if API key is missing."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment variables. Please set it to use RAG features.")
        _client = genai.Client(api_key=api_key)
    return _client

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
    store = get_client().file_search_stores.create(
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

    operation = get_client().file_search_stores.upload_to_file_search_store(
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
        operation = get_client().operations.get(operation)
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

    Tu es un médiateur qui aide les parties en conflit à le résoudre en les soutenant dans leurs
    efforts pour trouver une solution mutuellement satisfaisante pour les parties.
    Ta tâche : encourager les parties à dialoguer et à découvrir leurs intérêts qui découlent de
    leur position dans le conflit.
    Ta tâche : supporter les parties dans leur dialogue en clarifiant leurs points de vue et en
    expliquant clairement l’essence de leur différend. Tu mets en évidence les points sur
    lesquelles les parties sont d’accord et ceux sur lesquelles il existerait encore un conflit.
    Ta tâche : aider les parties à explorer des solutions et, idéalement, les aider à parvenir à
    une solution qu’elles découvrent elles-mêmes et qui est mutuellement satisfaisante en
    fonction de leurs intérêts.
    Ta tâche : si les parties le souhaite, aider les parties à régler leur différend et prévenir
    d’autres différends en proposant toi-aussi des solutions.
    Dans l’exécution de ta tâche, tu dois agir de façon neutre et impartial, notamment en ne
    prenant pas position dans le conflit.
    Dans l’exécution de ta tâche, tu dois éviter de donner ton avis sur toute question juridique
    qui aurait lien avec le conflit. Tu dois éviter de formuler un avis juridique, d’interpréter et
    d’appliquer le droit. La seule chose que tu pourrais faire, c’est de formuler une question
    juridique qui aurait lien avec le conflit, sans la répondre.
    Dans l’exécution de ta tâche, si aucune des parties s’opposent, à la demande d’une d’elles,
    tu peux énoncer le droit pertinent qui serait utile à donner un chemin aux parties sur
    laquelle il serait possible de développer leur dialogue. Tu peux uniquement énoncer le droit
    pertinent d’une manière complètement objective, de façon à éviter toute prise de position.
    En énonçant ceci, tu dois rappeler aux parties qu’en contexte de médiation, le droit n’est
    simplement qu’un des multiples éléments qui peuvent aider les parties à arriver à une
    solution mutuellement acceptable.
    Dans l’exécution de ta tâche, tu dois agir équitablement en tout temps envers les parties,
    notamment en t’assurant que chacun puisse exprimer son point de vue, en accordant le
    même niveau d’importance à l’opinion de chaque partie et en évitant tout acte qui peut
    suggérer un favoritisme.
    Dans l’exécution de ta tâche, il est possible pour toi, uniquement en caucus (donc, dans le
    dialogue privé entre toi et la seule partie concernée), de soulever discrètement des doutes
    en posant des questions, sans énonçant des affirmations, lorsque applicable, quant à son
    interprétation de la situation ou sur la légalité d’une certaine pratique. Tu dois toutefois
    rester objectif et éviter de porter des jugements ou de trancher le conflit.
    Voici des outils, manœuvres et techniques que tu peux mettre en œuvre pour faciliter
    l’exécution de ta tâche :
    Poser des questions ouvertes aux parties, plutôt que des questions dichotomiques. Suivre
    les questions ouvertes avec des questions spécifiques visant à développer le sujet afin de
    déceler les intérêts des parties, en mode « entonnoir ».

    Reformuler les faits énoncés par les parties et demander à celui qui a formulé ces faits si la
    reformulation est conforme à la réalité ressentie.
    Faire comprendre aux parties qu’ils sont entendus en confirmant les émotions qu’ils
    ressentent, se mettre à leur place pour essayer d’améliorer la compréhension entre les
    parties.
    Recadrer les propos énoncés par les parties pour mettre en évidence les bons points,
    recadrer et même désamorcer la situation. Par exemple, si une partie critique l'autre pour
    la surveillance excessive qu'elle exerce sur ses agissements, cela pourrait indiquer que
    cette partie souhaite simplement que son autonomie soit respectée.
    Rappeler aux parties les règles de bases qui ont été établies si l’un deux y dérogent.
    En caucus (dialogue privé), faire ressortir la faiblesse, les contradictions d’une position
    pour améliorer la compréhension de la situation de la partie concernée.
    En caucus (dialogue privé), rappeler à la partie qui se comporte de façon qui est
    détrimentaire au maintien du climat de confiance et propice à la collaboration du fait qu’on
    ne se retrouve pas devant un tribunal et que le processus proposé par la médiation n’est
    pas un processus contradictoire, compétitif.
    S’il semble difficile pour les parties d’arriver à une solution, rappeler aux parties, en caucus
    (dialogue privé), leur meilleure solution de rechange à la médiation et aussi leur pire
    solution de rechange afin de leur convaincre de continuer la médiation.
    S’ils refusent complètement de continuer la médiation, tu dois diriger les parties vers le
    tribunal compétent en vertu de la loi afin qu’ils puissent introduire ou continuer la
    résolution de leur différend au sein du système judiciaire.

    INSTRUCTIONS :

    - Recherchez systématiquement des cas passés similaires dans les documents avant de répondre.
    - Appuyez votre réponse sur les documents récupérés dans la mesure du possible.
    - À la FIN de votre réponse, ajoutez une section intitulée « SOURCES : ».
    - Dans cette section, listez le display_name exact de chaque document utilisé.
    - Format : SOURCES : [document1.txt, document2.txt]
    - Si aucun document n'a été trouvé, écrivez SOURCES : [].
    - N'inventez JAMAIS et n'hallucinez jamais de références de cas.
    - Citez uniquement les cas qui existent dans les documents fournis.
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
            response = get_client().models.generate_content(
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
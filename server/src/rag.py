import json
import os
import re
import time
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Content,
    Part,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

load_dotenv()

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------

_initialized = False
MODEL = "gemini-2.5-flash"
_gemini_disabled_until = 0.0

def get_client():
    """Lazy initialization of Vertex AI to avoid crash if credentials are missing."""
    global _initialized
    if not _initialized:
        project_id = os.environ.get("GCP_PROJECT_ID")
        location = os.environ.get("GCP_LOCATION", "us-central1")
        if not project_id:
            raise ValueError("GCP_PROJECT_ID is not set in environment variables. Please set it to use Vertex AI features.")
        vertexai.init(project=project_id, location=location)
        _initialized = True
    return GenerativeModel(MODEL)


def _gemini_is_temporarily_disabled() -> bool:
    return time.monotonic() < _gemini_disabled_until


def _disable_gemini_for(seconds: float) -> None:
    global _gemini_disabled_until
    _gemini_disabled_until = max(_gemini_disabled_until, time.monotonic() + seconds)


def _local_mediation_reply(user_message: str) -> str:
    lowered = user_message.lower()

    if any(keyword in lowered for keyword in ["accord", "d'accord", "agree", "oui"]):
        return "Je note une ouverture vers un accord. Essayez de préciser un point concret que vous acceptez tous les deux."

    if any(keyword in lowered for keyword in ["non", "refuse", "désaccord", "pas", "problème"]):
        return "Le point de blocage semble être précis. Pouvez-vous le reformuler en un besoin ou une limite acceptable pour chacun ?"

    return "Essayez de distinguer ce qui est non négociable de ce qui peut être ajusté. Un compromis clair peut souvent débloquer la discussion."


def _local_public_mediation(public_messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not public_messages:
        return {
            "reply": "La médiation est prête. Commencez la discussion dans le chat public.",
            "agreements": [],
            "disagreements": [],
            "compromises": [],
        }

    transcript = "\n".join(
        f"{message.get('sender', 'Participant')}: {message.get('text', '')}"
        for message in public_messages[-12:]
    )
    lowered = transcript.lower()

    agreements = []
    disagreements = []
    compromises = []

    if any(keyword in lowered for keyword in ["d'accord", "accord", "agree", "ok", "oui"]):
        agreements.append({"text": "Les parties cherchent une base commune."})

    if any(keyword in lowered for keyword in ["non", "refuse", "désaccord", "pas", "problème"]):
        disagreements.append({"text": "Un point précis bloque encore la discussion."})

    if len(agreements) == 0 and len(disagreements) == 0:
        agreements.append({"text": "La discussion reste ouverte et orientée vers la recherche d'une solution."})

    compromises.append({"text": "Clarifier le besoin de chaque partie et tester une option intermédiaire concrète."})
    compromises.append({"text": "Définir un engagement minimal acceptable pour avancer."})

    return {
        "reply": "Je vous invite à clarifier ce que chacun veut obtenir et à chercher un terrain d'entente concret.",
        "agreements": agreements,
        "disagreements": disagreements,
        "compromises": compromises,
    }


def _format_message_lines(messages: list[dict[str, Any]], limit: int = 12) -> str:
    recent_messages = messages[-limit:]
    return "\n".join(
        f"{message.get('sender', 'Participant')}: {message.get('text', '')}"
        for message in recent_messages
    )

router = APIRouter()


# -------------------------------------------------------
# Store Management
# -------------------------------------------------------

def create_store(display_name: str) -> str:
    """
    Create a new Vertex AI Search Datastore.
    Call this ONCE when setting up the project — save the returned
    store name in your .env as FILE_SEARCH_STORE_NAME.
    """
    # Note: With Vertex AI, search datastores are typically created via Google Cloud Console
    # or using the Vertex AI Search API. For now, this is a placeholder.
    print(f"Vertex AI Search datastores should be created via Google Cloud Console")
    print(f"Store display name: {display_name}")
    return "projects/{project}/locations/{location}/dataStores/{datastore_id}"


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
    Upload and index a legal document (PDF, TXT, DOCX) into Vertex AI Search.
    Note: Vertex AI Search indexing is typically handled through the Vertex AI Search API.
    """
    store_name = get_store_name()
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"Ingesting {path.name} into Vertex AI Search datastore {store_name}...")
    print(f"Metadata: {metadata}")
    print("Note: File indexing should be done via Vertex AI Search API or Google Cloud Console")
    # Implementation would use google.cloud.discoveryengine to index documents
    # For now, this logs the intended action


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

def query_rag(
    user_message: str,
    history: list[Content] = [],
    room_context: dict[str, Any] | None = None,
) -> dict:
    """
    Send a message to Vertex AI with Search enabled on every call.
    Supports multi-turn conversation via history.
    Returns { "reply": str, "sources": list[str] }
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return {
            "reply": _local_mediation_reply(user_message),
            "sources": [],
        }

    if _gemini_is_temporarily_disabled():
        return {
            "reply": _local_mediation_reply(user_message),
            "sources": [],
        }

    store_name = os.environ.get("FILE_SEARCH_STORE_NAME")

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

    Durant la médiation, tu dois suivre ses étapes pour le bon fonctionnement de la médiation.
    Premièrement, lorsque les deux parties entrent dans la salle de médiation, tu dois
    introduire les parties à la médiation en expliquant son caractère confidentiel. Tu mentionne
    que les parties peuvent, si tous sont d’accord, assujettir la médiation à des règles qu’ils
    accepteraient de respecter, à condition que ceux-ci ne dérogent pas à ce que tu es interdit
    de faire.
    Deuxièmement, tu répète les principes et règles énoncés à la première étape, notamment
    tes devoirs en tant que médiateur, dans le but de chercher l’accord des parties, c’est-à-dire
    tu cherches à ce que les parties expriment explicitement leur accord avec les règles que tu
    mentionne. Tu ne peux pas procéder à la troisième étape si les parties n’arrivent pas à un
    accord. Permet aux parties de débattre sur ce sujet tant qu’ils n’arrivent pas à un accord.
    Troisièmement, tu dois permettre aux parties d’énoncer leur version des faits. Accorde
    beaucoup d’importance à l’énonciation des points communs entre les versions de faits
    exposées, afin de favoriser le rapprochement des parties.
    Quatrièmement, tu dois discerner les intérêts des parties en utilisant les faits que chacun
    a évoqué. Tu dois permettre aux parties de corriger tes propos si une d’elle n’est pas
    d’accord. Attention, cependant, à la confusion entre les positions des parties et ses
    intérêts réels. Les intérêts sont à la source du conflit et servent à trouver la solution
    optimale, tandis que la position énoncée par chaque partie n’est qu’un indice qui permet à
    découvrir ses intérêts. L’intérêt n’est pas forcément financier, il peut aussi être, entre
    autres, la sécurité, la réparation de la relation entre les parties et la célérité dans le
    règlement du conflit.
    Cinquièmement, tu vas devoir rappeler aux parties leurs intérêts et leur permettre de
    découvrir des solutions à leur conflit tout seul. Tu dois rappeler aux parties d’utiliser leur
    créativité pour découvrir des solutions dans le cadre d’une séance de brainstorming.
    Rappelle aussi aux parties que les solutions qui sont proposés ne lient personnes, ce sont
    simplement des idées qui peuvent éventuellement amener à la découverte de la solution
    optimale, conforme aux intérêts des parties. Fait des liens entre les intérêts des parties et
    les solutions qu’ils proposent.
    Sixièmement, rappelle toutes les solutions proposées par les parties. Mentionne aux
    parties qu’ils doivent maintenant commenter, évaluer ou même modifier les solutions
    proposés pour arriver au but de la médiation, qui est de découvrir une solution optimale
    qui serait conforme à la plus grande quantité des intérêts des parties.
    Septièmement, si les parties arrivent à une solution qui est mutuellement satisfaisante,
    félicite les parties sur leur entente et explique les qu’il faut maintenant vérifier une dernière
    fois que la solution est conforme à leurs intérêts, clarifier les points de l’entente et
    s’assurer de son caractère complet et de la compréhension des parties.

    S’il semble difficile pour les parties d’arriver à une solution, rappeler aux parties, en caucus
    (dialogue privé), leur meilleure solution de rechange à la médiation et aussi leur pire
    solution de rechange afin de leur convaincre de continuer la médiation.
    S’ils refusent complètement de continuer ou si la médiation n’a pas complètement résolu
    le conflit, tu dois diriger les parties vers le tribunal compétent en vertu de la loi afin qu’ils
    puissent introduire ou continuer la résolution de leur différend au sein du système
    judiciaire. Rappelez cependant aux parties l’utilité dont a fait preuve la médiation en
    répétant les petites ententes qu’ils ont réussi à avoir.

    Voici des outils, manœuvres et techniques que tu peux mettre en œuvre pour faciliter
    l’exécution de ta tâche. Si les parties ne discutent pas, sois proactif et utilise ces méthodes
    pour relancer la discussion et continuer l’exécution de ta tâche.
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

    context_sections: list[str] = []
    if room_context:
        public_messages = room_context.get("public_messages", []) or []

        if public_messages:
            context_sections.append(
                "Contexte public récent de la salle:\n" + _format_message_lines(public_messages)
            )

    contents = [
        Content(role="user", parts=[Part.from_text(system_prompt)]),
        Content(role="model", parts=[Part.from_text("Compris. Je suis prêt à vous aider.")]),
    ]

    if context_sections:
        contents.append(
            Content(role="user", parts=[Part.from_text("\n\n".join(context_sections))])
        )

    contents.extend([
        *history,
        Content(role="user", parts=[Part.from_text(user_message)])
    ])

    # Retry automatique si rate limit
    response = None
    for attempt in range(3):
        try:
            model = get_client()
            response = model.generate_content(
                contents=contents,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 2048,
                },
            )
            break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = (attempt + 1) * 30
                print(f"Rate limit. Waiting {wait}s...")
                time.sleep(wait)
            else:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    _disable_gemini_for(900)
                    return {"reply": _local_mediation_reply(user_message), "sources": []}
                raise

    if response is None:
        raise RuntimeError("Gemini response was not generated.")

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


def mediate_conversation(
    public_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a mediated summary for the public room chat using Gemini."""
    if not public_messages:
        return {
            "reply": "La médiation est prête. Commencez la discussion dans le chat public.",
            "agreements": [],
            "disagreements": [],
            "compromises": [],
        }

    transcript = _format_message_lines(public_messages)

    prompt = f"""
    Tu es un médiateur neutre.
    Analyse la conversation ci-dessous et retourne UNIQUEMENT du JSON valide sans markdown.

    Format exact attendu:
    {{
    "reply": "une réponse engageante et utile à montrer dans le chat public afin de continuer la conversation et d'obtenir le point de vue de chaque partie.",
    "agreements": [{{"text": "point d'accord"}}],
    "disagreements": [{{"text": "point de désaccord"}}],
    "compromises": [{{"text": "compromis suggéré"}}]
    }}
    \nConversation publique:\n{transcript}
    """.strip()

    try:
        #if _gemini_is_temporarily_disabled() or not os.environ.get("GEMINI_API_KEY"):
        #    return _local_public_mediation(public_messages)

        model = get_client()
        response = model.generate_content(
            contents=[Content(role="user", parts=[Part.from_text(prompt)])],
        )

        raw_text = (response.text or "").strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}")
        if json_start != -1 and json_end != -1:
            raw_text = raw_text[json_start:json_end + 1]

        parsed = json.loads(raw_text)
        return {
            "reply": str(parsed.get("reply", "")),
            "agreements": parsed.get("agreements", []),
            "disagreements": parsed.get("disagreements", []),
            "compromises": parsed.get("compromises", []),
        }
    except Exception as exc:
        print(exc)

        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            #_disable_gemini_for(900)
            return _local_public_mediation(public_messages)
        print(f"Mediation generation failed: {exc}")
        return _local_public_mediation(public_messages)


# -------------------------------------------------------
# Pydantic Models
# -------------------------------------------------------

class Message(BaseModel):
    role: str       # "user" or "model"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []
    roomCode: str | None = None
    senderName: str | None = None

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

def build_gemini_history(history: list[Message]) -> list[Content]:
    return [
        Content(
            role=msg.role,
            parts=[Part.from_text(msg.content)]
        )
        for msg in history
    ]


def _get_room_store():
    try:
        from .rooms import store as room_store
    except ImportError:
        from rooms import store as room_store

    return room_store


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint — every message triggers a RAG search.
    Supports multi-turn conversation via history.
    """
    try:
        gemini_history = build_gemini_history(request.history)
        room_context = None

        if request.roomCode:
            room_store = _get_room_store()
            try:
                room_context = {
                    "public_messages": room_store.get_room(request.roomCode).get("publicMessages", []),
                }
            except KeyError:
                room_context = None

        result = query_rag(request.message, gemini_history, room_context)

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
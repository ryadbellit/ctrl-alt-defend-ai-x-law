from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class Message(BaseModel):
    role: str    # "user" ou "model"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []

class ChatResponse(BaseModel):
    reply: str

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
    try:
        gemini_history = build_gemini_history(request.history)

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=gemini_history + [
                types.Content(
                    role="user",
                    parts=[types.Part(text=request.message)]
                )
            ],
        )

        return ChatResponse(reply=response.text)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
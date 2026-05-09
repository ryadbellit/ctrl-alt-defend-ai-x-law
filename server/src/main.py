from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from .rag import router as rag_router
    from .rooms import router as rooms_router
except ImportError:
    from rag import router as rag_router
    from rooms import router as rooms_router

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router)
app.include_router(rooms_router)

@app.get("/")
def root():
    return {"message": "Hello World"}
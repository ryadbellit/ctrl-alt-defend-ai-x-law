from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rag import router as rag_router
from chat import router as chat_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(rag_router)
app.include_router(chat_router)

@app.get("/")
def root():
    return {"message": "Hello World"}
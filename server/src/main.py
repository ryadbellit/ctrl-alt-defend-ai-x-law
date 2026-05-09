from fastapi import FastAPI

from rag import router as rag_router


app = FastAPI()
app.include_router(rag_router)

@app.get("/")
def root():
    return {"message": "Hello World"}
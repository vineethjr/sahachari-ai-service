from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from rag_engine import get_answer

app = FastAPI(
    title="Sahachari AI Service"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {
        "message": "Sahachari AI Service Running"
    }

@app.post("/chat")
def chat(req: ChatRequest):

    result = get_answer(
        req.message
    )

    return {
        "question": req.message,
        "answer": result["answer"],
        "source": result["source"]
    }
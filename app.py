from fastapi import FastAPI
from pydantic import BaseModel

from rag_engine import get_answer

app = FastAPI(
    title="Sahachari AI Service"
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
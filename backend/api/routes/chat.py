from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.agent import run_agent
from backend.db.database import get_db

router = APIRouter(prefix="/chat", tags=["chat"])


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    client_id: int | None = None
    portfolio_id: int | None = None


@router.post("/")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Accepts a conversation history and streams the agent's response back
    as plain text chunks (Server-Sent Events style).
    """
    # Inject portfolio context into the last user message if provided
    messages = [m.model_dump() for m in body.messages]
    if body.portfolio_id and messages:
        last = messages[-1]
        if last["role"] == "user":
            last["content"] = (
                f"[Context: portfolio_id={body.portfolio_id}]\n\n{last['content']}"
            )

    async def stream():
        async for chunk in run_agent(messages, db, client_id=body.client_id):
            yield chunk

    return StreamingResponse(stream(), media_type="text/plain")

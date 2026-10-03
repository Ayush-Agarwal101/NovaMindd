"""
NovaMindd — Direct multi-turn chat endpoint.

Bypasses the agent pipeline and calls the Ollama /api/chat endpoint
directly, so the frontend can have a plain ChatGPT-style conversation.

If a session_id is provided, document context from that session (and global
documents) is retrieved and prepended as a system message.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])

_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    role: str          # "user" | "assistant" | "system"
    content: str


class ChatCompleteRequest(BaseModel):
    model: str
    messages: list[ChatMessageIn]
    temperature: float = 0.7
    max_tokens: int = 2048
    session_id: str | None = None   # enables scoped document retrieval


class ChatCompleteResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/complete", response_model=ChatCompleteResponse)
async def chat_complete(body: ChatCompleteRequest) -> ChatCompleteResponse:
    """
    Send a full message history to the model and return its reply.

    When session_id is provided the last user message is used to retrieve
    relevant document context (global + session scope) which is injected as
    a system context block before the conversation.
    """
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    # ── Optional document context injection ──────────────────────────────────
    if body.session_id:
        try:
            from apps.api.dependencies import get_index_manager
            index_mgr = get_index_manager()

            # Use the last user message as the retrieval query
            user_turns = [m for m in body.messages if m.role == "user"]
            if user_turns:
                query = user_turns[-1].content
                evidence = index_mgr.retrieve_combined(
                    body.session_id, query, top_k=4
                )
                if evidence:
                    ctx_text = "\n\n---\n\n".join(
                        f"[{e.source_path} · p.{e.page}]\n{e.text}"
                        for e in evidence
                    )
                    system_msg = {
                        "role": "system",
                        "content": (
                            "Use the following document excerpts to answer "
                            "the user's question. "
                            "If the answer is not in the excerpts, say so.\n\n"
                            + ctx_text
                        ),
                    }
                    # Prepend context, keeping any existing system message last
                    messages = [system_msg] + messages
        except Exception:
            pass  # Never fail a chat request because of retrieval

    payload = {
        "model": body.model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": body.temperature,
            "num_predict": body.max_tokens,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{_OLLAMA_BASE}/api/chat", json=payload)
            r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Ollama error: {exc.response.text}"
        ) from exc
    except httpx.TransportError as exc:
        raise HTTPException(
            status_code=503, detail=f"Ollama unreachable: {exc}"
        ) from exc

    data = r.json()
    msg = data.get("message", {})
    usage = data.get("usage", {})

    return ChatCompleteResponse(
        content=msg.get("content", ""),
        model=data.get("model", body.model),
        prompt_tokens=usage.get("prompt_tokens", data.get("prompt_eval_count", 0)),
        completion_tokens=usage.get("completion_tokens", data.get("eval_count", 0)),
    )

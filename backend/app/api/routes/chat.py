from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.context import AgentContext
from app.agents.repository_agent import answer_repository_question
from app.agents.runner import AgentExecutionError
from app.api.deps import get_current_user, get_owned_repository
from app.core.config import get_settings
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.enums import MessageRole, RepositoryStatus
from app.models.message import Message
from app.models.repository import Repository
from app.models.user import User
from app.schemas.chat import ChatRequest, ConversationDetailRead, ConversationRead, MessageRead
from app.services.llm.factory import get_llm_provider
from app.services.vectorstore.chroma_store import get_vector_store

router = APIRouter(prefix="/repositories/{repository_id}", tags=["chat"])


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[ConversationRead]:
    rows = (
        db.query(Conversation)
        .filter(Conversation.repository_id == repository.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [ConversationRead.model_validate(r) for r in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailRead)
def get_conversation(
    conversation_id: uuid.UUID,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> ConversationDetailRead:
    convo = db.get(Conversation, conversation_id)
    if convo is None or convo.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    detail = ConversationDetailRead.model_validate(convo)
    detail.messages = [MessageRead.model_validate(m) for m in convo.messages]
    return detail


@router.post("/chat", response_model=MessageRead)
def chat(
    payload: ChatRequest,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageRead:
    if repository.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready for chat yet (status={repository.status.value}).",
        )

    if payload.conversation_id:
        convo = db.get(Conversation, payload.conversation_id)
        if convo is None or convo.repository_id != repository.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    else:
        convo = Conversation(repository_id=repository.id, user_id=current_user.id, title=payload.message[:80])
        db.add(convo)
        db.flush()

    user_msg = Message(conversation_id=convo.id, role=MessageRole.USER, content=payload.message)
    db.add(user_msg)
    db.commit()

    settings = get_settings()
    ctx = AgentContext(db=db, settings=settings, repository=repository, vector_store=get_vector_store())
    provider = get_llm_provider()

    try:
        answer = answer_repository_question(ctx, provider, payload.message)
    except AgentExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"The Repository Agent failed to answer: {exc}"
        ) from exc

    assistant_msg = Message(
        conversation_id=convo.id,
        role=MessageRole.ASSISTANT,
        content=answer.text,
        citations=[c.__dict__ for c in answer.citations],
        token_usage=answer.token_usage,
    )
    db.add(assistant_msg)
    convo.title = convo.title or payload.message[:80]
    db.commit()
    db.refresh(assistant_msg)

    return MessageRead.model_validate(assistant_msg)

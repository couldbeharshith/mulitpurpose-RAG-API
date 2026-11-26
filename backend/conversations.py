"""Local workspace conversations and their original sources."""

import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import BinaryIO
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError

from backend.config import Config
from backend.models import HackRXRequest


router = APIRouter(prefix="/api/v1/conversations")
directory = Path(__file__).resolve().parents[1] / "chat-data"
lock = RLock()


class ConversationSource(BaseModel):
    name: str
    url: str | None = None
    size: int | None = None
    content_type: str = ""


class SavedTurn(BaseModel):
    question: str
    answer: str


class Conversation(BaseModel):
    id: UUID
    title: str
    source: ConversationSource
    turns: list[SavedTurn] = Field(default_factory=list)
    pinned: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    manual_title: bool = False
    starter: str | None = None


class ConversationChanges(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    pinned: bool | None = None


def get_conversation(conversation_id: UUID) -> Conversation:
    try:
        data = (directory / str(conversation_id) / "conversation.json").read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(404, "Conversation not found.") from exc
    return Conversation.model_validate_json(data)


def save_conversation(conversation: Conversation) -> None:
    folder = directory / str(conversation.id)
    with NamedTemporaryFile(dir=folder, delete=False) as temporary:
        path = Path(temporary.name)
        try:
            temporary.write(conversation.model_dump_json().encode("utf-8"))
            temporary.flush()
            temporary.close()
            os.replace(path, folder / "conversation.json")
        finally:
            path.unlink(missing_ok=True)


def copy_upload(upload: BinaryIO, destination: Path) -> int:
    limit = Config.MAX_DOCUMENT_SIZE_MB * 1024**2
    size = 0
    with destination.open("xb") as output:
        while block := upload.read(1024**2):
            size += len(block)
            if size > limit:
                raise HTTPException(413, f"Choose a file up to {Config.MAX_DOCUMENT_SIZE_MB} MB.")
            output.write(block)
    if not size:
        raise HTTPException(422, "This file is empty.")
    return size


@router.get("", response_model=list[Conversation])
def list_conversations():
    conversations = []
    for path in directory.glob("*/conversation.json"):
        try:
            conversations.append(get_conversation(UUID(path.parent.name)))
        except (ValueError, ValidationError, HTTPException):
            continue
    return sorted(conversations, key=lambda chat: (chat.pinned, chat.updated_at), reverse=True)


@router.post("", status_code=201, response_model=Conversation)
def create_conversation(name: str = Form(min_length=1, max_length=2048),
                        file: UploadFile | None = File(None), url: str | None = Form(None),
                        starter: str | None = Form(None, max_length=1000)):
    if bool(file) == bool(url):
        raise HTTPException(422, "Choose one file or one source link.")
    if url:
        try:
            url = HackRXRequest.validate_url(url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    source = ConversationSource(name=name, url=url, content_type=(file.content_type or "") if file else "")
    conversation = Conversation(id=uuid4(), title=name[:100], source=source, starter=starter)
    folder = directory / str(conversation.id)
    folder.mkdir(parents=True)
    try:
        if file:
            conversation.source.size = copy_upload(file.file, folder / "source")
        save_conversation(conversation)
    except Exception:
        (folder / "source").unlink(missing_ok=True)
        folder.rmdir()
        raise
    return conversation


def read_source(conversation_id: UUID) -> bytes:
    with lock:
        try:
            return (directory / str(conversation_id) / "source").read_bytes()
        except FileNotFoundError as exc:
            raise HTTPException(410, "The saved source file is missing.") from exc


def append_turns(conversation_id: UUID, expected_count: int, turns: list[SavedTurn],
                 generated_title: str | None) -> Conversation:
    with lock:
        conversation = get_conversation(conversation_id)
        if len(conversation.turns) != expected_count:
            raise HTTPException(409, "This conversation changed. Reload it before sending again.")
        if generated_title and not conversation.turns and not conversation.manual_title:
            conversation.title = generated_title
        conversation.turns.extend(turns)
        conversation.updated_at = datetime.now(timezone.utc)
        save_conversation(conversation)
        return conversation


@router.patch("/{conversation_id}", response_model=Conversation)
def change_conversation(conversation_id: UUID, changes: ConversationChanges):
    with lock:
        conversation = get_conversation(conversation_id)
        if changes.title is not None:
            title = changes.title.strip()
            if not title:
                raise HTTPException(422, "Enter a conversation title.")
            conversation.title = title
            conversation.manual_title = True
        if changes.pinned is not None:
            conversation.pinned = changes.pinned
        save_conversation(conversation)
        return conversation


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID):
    with lock:
        get_conversation(conversation_id)
        folder = directory / str(conversation_id)
        removed = folder.rename(directory / f".deleted-{conversation_id}")
        (removed / "conversation.json").unlink()
        (removed / "source").unlink(missing_ok=True)
        removed.rmdir()

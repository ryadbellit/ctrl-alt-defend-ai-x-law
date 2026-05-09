from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from random import choice
from string import digits
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

try:
    from .rag import mediate_conversation
except ImportError:
    from rag import mediate_conversation

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initial(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip() if ch.isalnum())
    return (cleaned[:1] or "?").upper()


def _generate_code() -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    prefix = "".join(choice(letters) for _ in range(3))
    suffix = "".join(choice(digits) for _ in range(4))
    return f"{prefix}-{suffix}"


def _empty_insights() -> dict[str, Any]:
    return {
        "reply": "",
        "agreements": [],
        "disagreements": [],
        "compromises": [],
    }


class CreateRoomRequest(BaseModel):
    name: str
    code: str | None = None


class JoinRoomRequest(BaseModel):
    name: str


class RoomStore:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, Any]] = {}

    def _unique_code(self, requested_code: str | None = None) -> str:
        requested_code = requested_code.upper().strip() if requested_code else None

        if requested_code and requested_code not in self.rooms:
            return requested_code

        code = _generate_code()
        while code in self.rooms:
            code = _generate_code()

        return code

    def _serialize(self, room: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": room["code"],
            "hostName": room["hostName"],
            "participants": room["participants"],
            "createdAt": room["createdAt"],
            "publicMessages": room["publicMessages"],
            "insights": room["insights"],
        }

    def create_room(self, name: str, requested_code: str | None = None) -> dict[str, Any]:
        code = self._unique_code(requested_code)

        room = {
            "code": code,
            "hostName": name,
            "participants": [
                {
                    "name": name,
                    "role": "Host",
                    "initial": _initial(name),
                    "color": "#3b82f6",
                    "online": True,
                }
            ],
            "createdAt": _now_iso(),
            "publicMessages": [],
            "insights": _empty_insights(),
        }

        self.rooms[code] = room
        return self._serialize(room)

    def append_public_message(self, code: str, sender: str, text: str, role: str = "participant", is_ai: bool = False) -> dict[str, Any]:
        code = code.upper().strip()
        room = self.rooms.get(code)

        if not room:
            raise KeyError(f"Room {code} not found")

        message = {
            "sender": sender,
            "role": role,
            "time": _now_iso(),
            "text": text,
            "isAI": is_ai,
        }

        room["publicMessages"].append(message)
        return self._serialize(room)

    def update_insights(self, code: str, insights: dict[str, Any]) -> dict[str, Any]:
        code = code.upper().strip()
        room = self.rooms.get(code)

        if not room:
            raise KeyError(f"Room {code} not found")

        room["insights"] = {
            "reply": insights.get("reply", ""),
            "agreements": insights.get("agreements", []),
            "disagreements": insights.get("disagreements", []),
            "compromises": insights.get("compromises", []),
        }

        return self._serialize(room)

    def join_room(self, code: str, name: str) -> dict[str, Any]:
        code = code.upper().strip()
        room = self.rooms.get(code)

        if not room:
            raise KeyError(f"Room {code} not found")

        participant_names = {p["name"] for p in room["participants"]}

        if name not in participant_names:
            room["participants"].append(
                {
                    "name": name,
                    "role": "Participant",
                    "initial": _initial(name),
                    "color": "#a855f7",
                    "online": True,
                }
            )

        return self._serialize(room)

    def get_room(self, code: str) -> dict[str, Any]:
        code = code.upper().strip()
        room = self.rooms.get(code)

        if not room:
            raise KeyError(f"Room {code} not found")

        return self._serialize(room)


class RoomConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, code: str, websocket: WebSocket) -> None:
        await websocket.accept()
        code = code.upper().strip()
        self.connections.setdefault(code, []).append(websocket)

    def disconnect(self, code: str, websocket: WebSocket) -> None:
        code = code.upper().strip()
        sockets = self.connections.get(code, [])

        if websocket in sockets:
            sockets.remove(websocket)

        if not sockets and code in self.connections:
            del self.connections[code]

    async def broadcast_room_state(self, code: str, room: dict[str, Any]) -> None:
        code = code.upper().strip()
        sockets = self.connections.get(code, [])

        disconnected: list[WebSocket] = []

        for socket in sockets:
            try:
                await socket.send_json({
                    "type": "room_state",
                    "room": room,
                })
            except Exception:
                disconnected.append(socket)

        for socket in disconnected:
            self.disconnect(code, socket)


store = RoomStore()
manager = RoomConnectionManager()


@router.post("")
async def create_room(request: CreateRoomRequest):
    room = store.create_room(
        name=request.name.strip() or "Host",
        requested_code=request.code,
    )

    await manager.broadcast_room_state(room["code"], room)

    return room


@router.get("/{code}")
def get_room(code: str):
    try:
        return store.get_room(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{code}/join")
async def join_room(code: str, request: JoinRoomRequest):
    try:
        room = store.join_room(code, request.name.strip() or "Guest")
        await manager.broadcast_room_state(code, room)
        return room
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.websocket("/{code}/ws")
async def room_socket(websocket: WebSocket, code: str):
    code = code.upper().strip()

    try:
        room = store.get_room(code)
    except KeyError:
        await websocket.accept()
        await websocket.send_json({
            "type": "room_error",
            "message": f"Room {code} not found",
        })
        await websocket.close()
        return

    await manager.connect(code, websocket)

    try:
        await websocket.send_json({
            "type": "room_state",
            "room": room,
        })

        while True:
            raw_message = await websocket.receive_text()

            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "room_error",
                    "message": "Invalid JSON payload.",
                })
                continue

            action = payload.get("action")

            if action == "send_public_message":
                sender = (payload.get("sender") or "Guest").strip() or "Guest"
                text = (payload.get("text") or "").strip()

                if not text:
                    continue

                room = store.append_public_message(code, sender, text)
                await manager.broadcast_room_state(code, room)

                insights = await asyncio.to_thread(
                    mediate_conversation,
                    room["publicMessages"],
                )
                ai_reply = (insights.get("reply") or "").strip()

                if ai_reply:
                    room = store.append_public_message(
                        code,
                        "AI Mediator",
                        ai_reply,
                        role="ai",
                        is_ai=True,
                    )

                room = store.update_insights(code, insights)
                await manager.broadcast_room_state(code, room)

            elif action == "get_room":
                await websocket.send_json({
                    "type": "room_state",
                    "room": store.get_room(code),
                })
            else:
                await websocket.send_json({
                    "type": "room_error",
                    "message": f"Unknown action: {action}",
                })

    except WebSocketDisconnect:
        manager.disconnect(code, websocket)
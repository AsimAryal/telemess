"""Main FastAPI application for Telemess."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .game_manager import game_manager
from .websocket_handler import websocket_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup - initialize database and start cleanup loop
    await game_manager.initialize()
    print("Telemess server started - database initialized")
    yield
    # Shutdown
    print("Telemess server shutting down")


app = FastAPI(
    title="Telemess",
    description="The drawing game where things go hilariously wrong",
    version="0.1.0",
    lifespan=lifespan,
)

# Get the directory containing this file
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main game page."""
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Telemess</h1><p>Static files not found.</p>")


@app.get("/api/rooms")
async def get_rooms() -> list[dict[str, Any]]:
    """Get list of available rooms."""
    return await game_manager.get_available_rooms()


@app.post("/api/rooms")
async def create_room(request: Request) -> JSONResponse:
    """Create a new game room."""
    data = await request.json()
    host_name = data.get("host_name", "Anonymous")
    room_name = data.get("room_name", "")

    room, host = await game_manager.create_room(host_name, room_name)

    # Get full room data with players
    full_room = await game_manager.get_room(room["id"])

    return JSONResponse(
        {
            "room_id": room["id"],
            "player_id": host["id"],
            "room": _room_to_response(full_room),
        }
    )


@app.post("/api/rooms/{room_id}/join")
async def join_room(room_id: str, request: Request) -> JSONResponse:
    """Join an existing room."""
    data = await request.json()
    player_name = data.get("player_name", "Anonymous")
    player_id = data.get("player_id")  # For reconnection

    result = await game_manager.join_room(room_id, player_name, player_id)

    if not result:
        return JSONResponse({"error": "Room not found or full"}, status_code=404)

    room, player = result

    return JSONResponse(
        {
            "room_id": room["id"],
            "player_id": player["id"],
            "room": _room_to_response(room),
        }
    )


def _room_to_response(room: dict[str, Any] | None) -> dict[str, Any]:
    """Convert room data to API response format."""
    if not room:
        return {}

    players = {
        pid: {
            "id": p["id"],
            "name": p["name"],
            "is_host": p["is_host"],
            "is_connected": p["is_connected"],
        }
        for pid, p in room.get("players", {}).items()
    }

    return {
        "id": room["id"],
        "name": room["name"],
        "phase": room["phase"],
        "settings": room["settings"],
        "players": players,
        "player_count": len(players),
    }


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_route(websocket: WebSocket, room_id: str, player_id: str):
    """WebSocket endpoint for real-time game communication."""
    await websocket_endpoint(websocket, room_id, player_id)


def run():
    """Run the application."""
    from pathlib import Path

    # Determine app_dir (src directory)
    src_dir = Path(__file__).resolve().parent.parent
    uvicorn.run(
        "telemess.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir=str(src_dir),
    )


if __name__ == "__main__":
    run()

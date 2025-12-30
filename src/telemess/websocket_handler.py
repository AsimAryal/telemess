"""WebSocket handler for real-time game communication."""

import asyncio
import time
from typing import Any

from fastapi import WebSocket

from .game_manager import game_manager


class ConnectionManager:
    """Manages WebSocket connections for all players."""

    def __init__(self):
        # room_id -> player_id -> WebSocket
        self.connections: dict[str, dict[str, WebSocket]] = {}
        # player_id -> (room_id, WebSocket)
        self.player_connections: dict[str, tuple[str, WebSocket]] = {}
        # Timing tasks for each room
        self.timing_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, room_id: str, player_id: str):
        """Register a new connection."""
        await websocket.accept()

        if room_id not in self.connections:
            self.connections[room_id] = {}

        # Close old connection if exists
        if player_id in self.connections[room_id]:
            try:
                await self.connections[room_id][player_id].close()
            except Exception:
                pass

        self.connections[room_id][player_id] = websocket
        self.player_connections[player_id] = (room_id, websocket)

        # Reconnect player in game manager
        await game_manager.reconnect_player(room_id, player_id)

    def disconnect(self, room_id: str, player_id: str):
        """Remove a connection."""
        if room_id in self.connections and player_id in self.connections[room_id]:
            del self.connections[room_id][player_id]
            if not self.connections[room_id]:
                del self.connections[room_id]

        if player_id in self.player_connections:
            del self.player_connections[player_id]

    async def mark_player_disconnected(self, room_id: str, player_id: str):
        """Mark player as disconnected in the database."""
        await game_manager.disconnect_player(room_id, player_id)

    async def send_personal(
        self, message: dict[str, Any], room_id: str, player_id: str
    ):
        """Send a message to a specific player."""
        if room_id in self.connections and player_id in self.connections[room_id]:
            try:
                await self.connections[room_id][player_id].send_json(message)
            except Exception:
                self.disconnect(room_id, player_id)

    async def broadcast_room(
        self, message: dict[str, Any], room_id: str, exclude: str | None = None
    ):
        """Send a message to all players in a room."""
        if room_id not in self.connections:
            return

        disconnected = []
        for player_id, ws in self.connections[room_id].items():
            if player_id == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(player_id)

        for player_id in disconnected:
            self.disconnect(room_id, player_id)

    async def handle_message(
        self, websocket: WebSocket, room_id: str, player_id: str, data: dict
    ):
        """Handle incoming WebSocket messages."""
        msg_type = data.get("type", "")
        room = await game_manager.get_room(room_id)

        if not room:
            await websocket.send_json({"type": "error", "message": "Room not found"})
            return

        if msg_type == "ping":
            await websocket.send_json({"type": "pong", "timestamp": time.time()})

        elif msg_type == "get_state":
            await self._send_game_state(room_id, player_id)

        elif msg_type == "update_settings":
            player = room["players"].get(player_id)
            if player and player["is_host"]:
                await game_manager.update_settings(room_id, data.get("settings", {}))
                await self._broadcast_room_state(room_id)

        elif msg_type == "start_game":
            player = room["players"].get(player_id)
            if player and player["is_host"]:
                can_start, error = await game_manager.can_start_game(room_id)
                if can_start:
                    await game_manager.start_game(room_id)
                    await self._broadcast_room_state(room_id)
                    await self._send_all_turn_info(room_id)
                    self._start_timer(room_id)
                else:
                    await websocket.send_json({"type": "error", "message": error})

        elif msg_type == "submit_turn":
            chain_id = data.get("chain_id", "")
            content = data.get("content", "")
            success, message = await game_manager.submit_turn(
                room_id, player_id, chain_id, content
            )

            if success:
                await self._broadcast_room_state(room_id)
                await self._send_all_turn_info(room_id)

                # Check if reveal phase started
                room = await game_manager.get_room(room_id)
                if room and room["phase"] == "reveal":
                    self._cancel_timer(room_id)
            else:
                await websocket.send_json({"type": "error", "message": message})

        elif msg_type == "advance_reveal":
            player = room["players"].get(player_id)
            if player and player["is_host"]:
                has_more = await game_manager.advance_reveal(room_id)
                await self._broadcast_room_state(room_id)
                if not has_more:
                    await self.broadcast_room({"type": "game_finished"}, room_id)

        elif msg_type == "restart_game":
            player = room["players"].get(player_id)
            if player and player["is_host"]:
                await game_manager.restart_game(room_id)
                await self._broadcast_room_state(room_id)

        elif msg_type == "leave":
            still_exists = await game_manager.leave_room(room_id, player_id)
            self.disconnect(room_id, player_id)
            if still_exists:
                await self._broadcast_room_state(room_id)

    async def _send_game_state(self, room_id: str, player_id: str):
        """Send current game state to a player."""
        room = await game_manager.get_room(room_id)
        if not room:
            return

        # Convert room to serializable format
        room_data = self._room_to_dict(room)

        state = {
            "type": "game_state",
            "room": room_data,
            "your_id": player_id,
        }

        # Add turn info if in playing phase
        if room["phase"] == "playing":
            turn_info = await game_manager.get_player_turn_info(room_id, player_id)
            if turn_info:
                state["turn_info"] = turn_info

        await self.send_personal(state, room_id, player_id)

    def _room_to_dict(self, room: dict[str, Any]) -> dict[str, Any]:
        """Convert room data to a format suitable for the frontend."""
        players = {
            pid: {
                "id": p["id"],
                "name": p["name"],
                "is_host": p["is_host"],
                "is_connected": p["is_connected"],
            }
            for pid, p in room.get("players", {}).items()
        }

        result = {
            "id": room["id"],
            "name": room["name"],
            "phase": room["phase"],
            "settings": room["settings"],
            "players": players,
            "player_count": len(players),
            "connected_count": sum(1 for p in players.values() if p["is_connected"]),
        }

        # Include chains for reveal/finished phases
        if room["phase"] in ("reveal", "finished") and "chains" in room:
            result["chains"] = [
                {
                    "id": c["id"],
                    "turns": [
                        {
                            "id": t["id"],
                            "turn_type": t["turn_type"],
                            "player_id": t["player_id"],
                            "player_name": t["player_name"],
                            "content": t["content"],
                        }
                        for t in c.get("turns", [])
                    ],
                    "is_complete": c["is_complete"],
                }
                for c in room["chains"]
            ]
            result["reveal_chain_index"] = room.get("reveal_chain_index", 0)

        return result

    async def _send_all_turn_info(self, room_id: str):
        """Send turn info to all players in a room."""
        room = await game_manager.get_room(room_id)
        if not room or room["phase"] != "playing":
            return

        for player_id in room.get("players", {}):
            turn_info = await game_manager.get_player_turn_info(room_id, player_id)
            if turn_info:
                await self.send_personal(
                    {"type": "turn_info", "turn_info": turn_info},
                    room_id,
                    player_id,
                )

    async def _broadcast_room_state(self, room_id: str):
        """Broadcast room state to all players."""
        room = await game_manager.get_room(room_id)
        if not room:
            return

        for player_id in room.get("players", {}):
            await self._send_game_state(room_id, player_id)

    def _start_timer(self, room_id: str):
        """Start the turn timer for a room."""
        self._cancel_timer(room_id)
        self.timing_tasks[room_id] = asyncio.create_task(self._timer_loop(room_id))

    def _cancel_timer(self, room_id: str):
        """Cancel the timer for a room."""
        if room_id in self.timing_tasks:
            self.timing_tasks[room_id].cancel()
            del self.timing_tasks[room_id]

    async def _timer_loop(self, room_id: str):
        """Timer loop that checks for timeouts."""
        try:
            while True:
                await asyncio.sleep(1)

                room = await game_manager.get_room(room_id)
                if not room or room["phase"] != "playing":
                    break

                current_time = time.time()
                elapsed = current_time - room["current_turn_start"]
                settings = room["settings"]

                # Check each chain for timeout
                chains = room.get("chains", [])
                for chain in chains:
                    if chain["is_complete"]:
                        continue

                    # Determine current turn type and time limit
                    turns = chain.get("turns", [])
                    if not turns:
                        continue

                    last_turn = turns[-1]
                    is_drawing = last_turn["turn_type"] in ("prompt", "description")
                    time_limit = (
                        settings["draw_time"]
                        if is_drawing
                        else settings["describe_time"]
                    )

                    if elapsed >= time_limit:
                        await game_manager.force_submit_timeout(room_id, chain["id"])
                        await self._broadcast_room_state(room_id)
                        await self._send_all_turn_info(room_id)

                        # Re-fetch room to check phase
                        room = await game_manager.get_room(room_id)
                        if room and room["phase"] == "reveal":
                            return

                # Send timer sync every 30 seconds
                if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                    await self._send_timer_sync(room_id, elapsed)

        except asyncio.CancelledError:
            pass

    async def _send_timer_sync(self, room_id: str, elapsed: float):
        """Send lightweight timer sync to all players."""
        room = await game_manager.get_room(room_id)
        if not room or room["phase"] != "playing":
            return

        await self.broadcast_room(
            {
                "type": "timer_sync",
                "elapsed": elapsed,
                "current_turn_start": room["current_turn_start"],
            },
            room_id,
        )


# Global connection manager
connection_manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    """Main WebSocket endpoint handler."""
    await connection_manager.connect(websocket, room_id, player_id)

    try:
        # Send initial state
        await connection_manager._send_game_state(room_id, player_id)

        # Broadcast that player connected
        room = await game_manager.get_room(room_id)
        if room:
            await connection_manager.broadcast_room(
                {
                    "type": "player_connected",
                    "player_id": player_id,
                    "room": connection_manager._room_to_dict(room),
                },
                room_id,
            )

        # Listen for messages
        while True:
            data = await websocket.receive_json()
            await connection_manager.handle_message(websocket, room_id, player_id, data)

    except Exception:
        pass
    finally:
        connection_manager.disconnect(room_id, player_id)
        await connection_manager.mark_player_disconnected(room_id, player_id)

        # Broadcast that player disconnected
        room = await game_manager.get_room(room_id)
        if room:
            await connection_manager.broadcast_room(
                {
                    "type": "player_disconnected",
                    "player_id": player_id,
                    "room": connection_manager._room_to_dict(room),
                },
                room_id,
            )

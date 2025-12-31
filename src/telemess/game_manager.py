"""Game state management for Telemess using SQLite persistence."""

import asyncio
import random
import time
import uuid
from typing import Any

from . import database as db
from .logging_config import get_logger
from .prompts import get_random_prompts

logger = get_logger("game")


class GameManager:
    """Manages all game rooms and state with SQLite persistence."""

    # How long to keep disconnected players before removing (5 minutes)
    DISCONNECT_TIMEOUT = 300
    # How long to keep empty rooms (10 minutes)
    ROOM_CLEANUP_TIMEOUT = 600
    # How long to keep "connected" players who haven't been seen (30 minutes)
    # Handles browser crashes, network drops, etc.
    GHOST_TIMEOUT = 1800
    # Minimum players to start
    MIN_PLAYERS = 3

    def __init__(self):
        self._cleanup_task: asyncio.Task | None = None
        self._initialized = False

    async def initialize(self):
        """Initialize the database and start cleanup loop."""
        if self._initialized:
            return
        await db.init_db()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._initialized = True
        logger.info("GameManager initialized")

    async def _ensure_initialized(self):
        """Ensure the database is initialized before operations."""
        if not self._initialized:
            await self.initialize()

    async def _cleanup_loop(self):
        """Periodically clean up stale rooms and players."""
        logger.debug("Cleanup loop started")
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            try:
                players_removed, rooms_removed = await db.cleanup_stale_data(
                    self.DISCONNECT_TIMEOUT,
                    self.ROOM_CLEANUP_TIMEOUT,
                    self.GHOST_TIMEOUT,
                )
                if players_removed or rooms_removed:
                    logger.info(
                        f"Cleanup: removed {players_removed} stale players, "
                        f"{rooms_removed} empty rooms"
                    )
            except Exception:
                logger.exception("Error in cleanup loop")

    async def create_room(
        self, host_name: str, room_name: str = "", ip: str = ""
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Create a new game room with the given host."""
        room_id = str(uuid.uuid4())[:8].upper()
        player_id = str(uuid.uuid4())

        # Default settings
        settings = {
            "draw_time": 60,
            "describe_time": 30,
            "custom_prompt": "",
            "max_prompt_length": 50,
            "rush_warning_time": 10,
        }

        room = await db.create_room(
            room_id=room_id, name=room_name or f"{host_name}'s Game", settings=settings
        )

        host = await db.create_player(
            player_id=player_id, room_id=room_id, name=host_name, is_host=True
        )

        logger.info(
            f"ROOM CREATED | room={room_id} name='{room['name']}' "
            f"host={host_name} ip={ip}"
        )

        return room, host

    async def get_room(self, room_id: str) -> dict[str, Any] | None:
        """Get a room by ID with all related data."""
        room = await db.get_room(room_id)
        if not room:
            return None

        # Add players
        room["players"] = await db.get_room_players(room_id)

        # Add chains if in playing/reveal phase
        if room["phase"] in ("playing", "reveal", "finished"):
            room["chains"] = await db.get_room_chains(room_id)

        return room

    async def get_available_rooms(self) -> list[dict[str, Any]]:
        """Get list of joinable rooms."""
        await self._ensure_initialized()
        return await db.get_available_rooms()

    async def join_room(
        self,
        room_id: str,
        player_name: str,
        player_id: str | None = None,
        ip: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Join an existing room. Returns None if room doesn't exist or is full."""
        room = await db.get_room(room_id)
        if not room:
            logger.warning(f"JOIN FAILED | room={room_id} reason=not_found ip={ip}")
            return None

        player_count = await db.count_room_players(room_id)
        if player_count >= 16:
            logger.warning(
                f"JOIN FAILED | room={room_id} reason=room_full "
                f"player={player_name} ip={ip}"
            )
            return None

        # Check if this is a reconnecting player or switching rooms
        if player_id:
            existing_player = await db.get_player(player_id)
            if existing_player:
                if existing_player["room_id"] == room_id.upper():
                    # Reconnecting to same room
                    await db.update_player(
                        player_id, is_connected=True, last_seen=time.time()
                    )
                    room = await self.get_room(room_id)
                    logger.info(
                        f"PLAYER RECONNECTED | room={room_id} player={player_name} "
                        f"id={player_id[:8]}... ip={ip}"
                    )
                    return room, existing_player
                else:
                    # Player exists in a different room - remove them from old room
                    old_room_id = existing_player["room_id"]
                    await db.delete_player(player_id)
                    logger.info(
                        f"PLAYER SWITCHED ROOMS | from={old_room_id} to={room_id} "
                        f"player={player_name} id={player_id[:8]}... ip={ip}"
                    )

        # New player (or player who just switched rooms)
        new_player_id = player_id or str(uuid.uuid4())
        player = await db.create_player(
            player_id=new_player_id,
            room_id=room_id.upper(),
            name=player_name,
            is_host=False,
        )

        room = await self.get_room(room_id)
        connected_count = len(
            [p for p in room["players"].values() if p["is_connected"]]
        )

        logger.info(
            f"PLAYER JOINED | room={room_id} player={player_name} "
            f"id={new_player_id[:8]}... players={connected_count}/16 ip={ip}"
        )

        return room, player

    async def leave_room(self, room_id: str, player_id: str) -> bool:
        """Player leaves a room. Returns True if room still exists."""
        room = await db.get_room(room_id)
        if not room:
            return False

        player = await db.get_player(player_id)
        if not player:
            return True

        was_host = player["is_host"]
        player_name = player["name"]

        # In lobby, remove immediately. In game, mark as disconnected
        if room["phase"] == "lobby":
            await db.delete_player(player_id)
            logger.info(
                f"PLAYER LEFT | room={room_id} player={player_name} "
                f"id={player_id[:8]}... phase=lobby"
            )
        else:
            await db.update_player(player_id, is_connected=False, last_seen=time.time())
            logger.info(
                f"PLAYER LEFT | room={room_id} player={player_name} "
                f"id={player_id[:8]}... phase={room['phase']} (marked disconnected)"
            )

        # Handle host migration
        if was_host:
            new_host_id = await db.ensure_room_has_host(room_id)
            if new_host_id:
                new_host = await db.get_player(new_host_id)
                if new_host:
                    logger.info(
                        f"HOST MIGRATED | room={room_id} "
                        f"new_host={new_host['name']} id={new_host_id[:8]}..."
                    )

        # Delete empty rooms in lobby
        player_count = await db.count_room_players(room_id)
        if player_count == 0 and room["phase"] == "lobby":
            await db.delete_room(room_id)
            logger.info(f"ROOM DELETED | room={room_id} reason=empty")
            return False

        return True

    async def update_settings(
        self, room_id: str, settings: dict[str, Any], player_name: str = ""
    ) -> bool:
        """Update room settings. Only host can do this."""
        room = await db.get_room(room_id)
        if not room:
            return False

        current_settings = room["settings"]
        changes = []

        if "draw_time" in settings:
            new_val = max(15, min(180, int(settings["draw_time"])))
            if new_val != current_settings["draw_time"]:
                current_settings["draw_time"] = new_val
                changes.append(f"draw_time={new_val}s")

        if "describe_time" in settings:
            new_val = max(10, min(120, int(settings["describe_time"])))
            if new_val != current_settings["describe_time"]:
                current_settings["describe_time"] = new_val
                changes.append(f"describe_time={new_val}s")

        if "custom_prompt" in settings:
            max_len = current_settings.get("max_prompt_length", 50)
            new_val = str(settings["custom_prompt"])[:max_len]
            if new_val != current_settings.get("custom_prompt", ""):
                current_settings["custom_prompt"] = new_val
                if new_val:
                    changes.append(f"custom_prompt='{new_val}'")

        if changes:
            logger.debug(
                f"SETTINGS UPDATED | room={room_id} by={player_name} "
                f"changes=[{', '.join(changes)}]"
            )

        return await db.update_room(room_id, settings=current_settings)

    async def can_start_game(self, room_id: str) -> tuple[bool, str]:
        """Check if a game can be started."""
        room = await db.get_room(room_id)
        if not room:
            return False, "Room not found"

        connected = await db.get_connected_players(room_id)
        if len(connected) < self.MIN_PLAYERS:
            return False, f"Need at least {self.MIN_PLAYERS} players to start"
        if room["phase"] != "lobby":
            return False, "Game already in progress"
        return True, ""

    async def start_game(self, room_id: str, host_name: str = "") -> bool:
        """Start the game, creating chains for all players."""
        can_start, reason = await self.can_start_game(room_id)
        if not can_start:
            logger.warning(
                f"GAME START FAILED | room={room_id} reason={reason} host={host_name}"
            )
            return False

        room = await db.get_room(room_id)
        connected = await db.get_connected_players(room_id)
        player_ids = [p["id"] for p in connected]
        player_names = [p["name"] for p in connected]
        random.shuffle(player_ids)

        # Calculate number of chains (aim for 4-6 players per chain)
        num_players = len(player_ids)
        if num_players <= 6:
            num_chains = 1
        elif num_players <= 10:
            num_chains = 2
        else:
            num_chains = 3

        # Distribute players across chains
        players_per_chain = num_players // num_chains
        extra = num_players % num_chains

        idx = 0
        prompts = get_random_prompts(num_chains)
        settings = room["settings"]
        chain_prompts = []

        for i in range(num_chains):
            chain_id = str(uuid.uuid4())
            chain_size = players_per_chain + (1 if i < extra else 0)
            chain_player_order = player_ids[idx : idx + chain_size]
            idx += chain_size

            await db.create_chain(
                chain_id=chain_id, room_id=room_id, player_order=chain_player_order
            )

            # Add initial prompt
            if settings.get("custom_prompt") and i == 0:
                initial_prompt = settings["custom_prompt"]
            else:
                initial_prompt = prompts[i] if i < len(prompts) else prompts[0]

            chain_prompts.append(initial_prompt)

            host = await db.get_room_host(room_id)
            await db.create_turn(
                turn_id=str(uuid.uuid4()),
                chain_id=chain_id,
                turn_type="prompt",
                player_id=host["id"] if host else "",
                player_name=host["name"] if host else "Game",
                content=initial_prompt,
                position=0,
            )

            # Assign first player to this chain
            if chain_player_order:
                first_player_id = chain_player_order[0]
                await db.update_player(first_player_id, current_chain_id=chain_id)

        # Update room phase
        await db.update_room(room_id, phase="playing", current_turn_start=time.time())

        logger.info(
            f"GAME STARTED | room={room_id} players={num_players} "
            f"chains={num_chains} prompts={chain_prompts} "
            f"participants=[{', '.join(player_names)}]"
        )

        return True

    async def get_player_turn_info(
        self, room_id: str, player_id: str
    ) -> dict[str, Any] | None:
        """Get the current turn info for a player."""
        room = await db.get_room(room_id)
        if not room or room["phase"] != "playing":
            return None

        player = await db.get_player(player_id)
        if not player:
            return None

        chains = await db.get_room_chains(room_id)
        settings = room["settings"]

        for chain in chains:
            if chain["is_complete"]:
                continue

            try:
                player_idx = chain["player_order"].index(player_id)
            except ValueError:
                continue

            if player_idx != chain["current_player_index"]:
                continue

            # This is the player's turn
            last_turn = chain["turns"][-1] if chain["turns"] else None
            if not last_turn:
                continue

            next_turn_type = (
                "drawing"
                if last_turn["turn_type"] in ("prompt", "description")
                else "description"
            )

            # Calculate time remaining
            elapsed = time.time() - room["current_turn_start"]
            time_limit = (
                settings["draw_time"]
                if next_turn_type == "drawing"
                else settings["describe_time"]
            )
            time_remaining = max(0, time_limit - elapsed)

            return {
                "chain_id": chain["id"],
                "turn_type": next_turn_type,
                "previous_content": last_turn["content"],
                "previous_type": last_turn["turn_type"],
                "time_remaining": time_remaining,
                "time_limit": time_limit,
                "rush_warning_time": settings.get("rush_warning_time", 10),
                "max_length": settings.get("max_prompt_length", 50),
                "is_your_turn": True,
            }

        # Player is waiting
        return {
            "is_your_turn": False,
            "waiting": True,
            "chains_progress": await self._get_chains_progress(room_id),
        }

    async def _get_chains_progress(self, room_id: str) -> list[dict[str, Any]]:
        """Get progress info for all chains (for waiting players)."""
        chains = await db.get_room_chains(room_id)
        progress = []
        for i, chain in enumerate(chains):
            progress.append(
                {
                    "chain_number": i + 1,
                    "turns_complete": len(chain["turns"]),
                    "total_players": len(chain["player_order"]),
                    "is_complete": chain["is_complete"],
                }
            )
        return progress

    async def submit_turn(
        self, room_id: str, player_id: str, chain_id: str, content: str
    ) -> tuple[bool, str]:
        """Submit a turn. Returns (success, message)."""
        room = await db.get_room(room_id)
        if not room or room["phase"] != "playing":
            return False, "Game not in progress"

        player = await db.get_player(player_id)
        if not player:
            return False, "Player not found"

        chain = await db.get_chain(chain_id)
        if not chain:
            return False, "Chain not found"

        if chain["is_complete"]:
            return False, "Chain already complete"

        # Verify it's this player's turn
        try:
            player_idx = chain["player_order"].index(player_id)
        except ValueError:
            return False, "Player not in this chain"

        if player_idx != chain["current_player_index"]:
            return False, "Not your turn"

        # Determine turn type
        last_turn = await db.get_last_turn(chain_id)
        if not last_turn:
            return False, "No previous turn found"

        turn_type = (
            "drawing"
            if last_turn["turn_type"] in ("prompt", "description")
            else "description"
        )

        # Validate content
        settings = room["settings"]
        if turn_type == "description":
            content = content.strip()[: settings.get("max_prompt_length", 50)]
            if not content:
                return False, "Description cannot be empty"

        # Create the turn
        turn_count = await db.count_chain_turns(chain_id)
        await db.create_turn(
            turn_id=str(uuid.uuid4()),
            chain_id=chain_id,
            turn_type=turn_type,
            player_id=player_id,
            player_name=player["name"],
            content=content,
            position=turn_count,
        )

        # Clear player's current chain
        await db.update_player(player_id, current_chain_id=None)

        # Move to next player or complete chain
        new_index = chain["current_player_index"] + 1
        is_chain_complete = new_index >= len(chain["player_order"])

        if is_chain_complete:
            await db.update_chain(chain_id, is_complete=True)
        else:
            await db.update_chain(chain_id, current_player_index=new_index)
            # Assign chain to next player
            next_player_id = chain["player_order"][new_index]
            await db.update_player(next_player_id, current_chain_id=chain_id)

        # Reset turn timer
        await db.update_room(room_id, current_turn_start=time.time())

        # Check if all chains are complete
        chains = await db.get_room_chains(room_id)
        all_complete = all(c["is_complete"] for c in chains)
        if all_complete:
            await db.update_room(room_id, phase="reveal")

        # Log the turn
        content_preview = content[:30] if turn_type == "description" else "(drawing)"
        logger.info(
            f"TURN SUBMITTED | room={room_id} player={player['name']} "
            f"type={turn_type} content='{content_preview}' "
            f"chain_complete={is_chain_complete} all_complete={all_complete}"
        )

        return True, "Turn submitted"

    async def force_submit_timeout(self, room_id: str, chain_id: str) -> bool:
        """Force submit an empty turn due to timeout."""
        chain = await db.get_chain(chain_id)
        if not chain or chain["is_complete"]:
            return False

        current_idx = chain["current_player_index"]
        if current_idx >= len(chain["player_order"]):
            return False

        player_id = chain["player_order"][current_idx]
        player = await db.get_player(player_id)
        player_name = player["name"] if player else "Unknown"

        # Determine turn type
        last_turn = await db.get_last_turn(chain_id)
        if not last_turn:
            return False

        turn_type = (
            "drawing"
            if last_turn["turn_type"] in ("prompt", "description")
            else "description"
        )

        # Add timeout turn
        turn_count = await db.count_chain_turns(chain_id)
        await db.create_turn(
            turn_id=str(uuid.uuid4()),
            chain_id=chain_id,
            turn_type=turn_type,
            player_id=player_id,
            player_name=player_name,
            content="(timed out)" if turn_type == "description" else "",
            position=turn_count,
        )

        if player:
            await db.update_player(player_id, current_chain_id=None)

        new_index = current_idx + 1
        if new_index >= len(chain["player_order"]):
            await db.update_chain(chain_id, is_complete=True)
        else:
            await db.update_chain(chain_id, current_player_index=new_index)
            next_player_id = chain["player_order"][new_index]
            await db.update_player(next_player_id, current_chain_id=chain_id)

        await db.update_room(room_id, current_turn_start=time.time())

        # Check if all chains complete
        chains = await db.get_room_chains(room_id)
        all_complete = all(c["is_complete"] for c in chains)
        if all_complete:
            await db.update_room(room_id, phase="reveal")

        logger.warning(
            f"TURN TIMEOUT | room={room_id} player={player_name} type={turn_type}"
        )

        return True

    async def get_reveal_data(self, room_id: str) -> dict[str, Any] | None:
        """Get the data for the reveal phase."""
        room = await db.get_room(room_id)
        if not room or room["phase"] not in ("reveal", "finished"):
            return None

        chains = await db.get_room_chains(room_id)

        return {
            "chains": chains,
            "current_chain_index": room["reveal_chain_index"],
            "total_chains": len(chains),
        }

    async def advance_reveal(self, room_id: str, host_name: str = "") -> bool:
        """Advance to the next chain in the reveal."""
        room = await db.get_room(room_id)
        if not room or room["phase"] != "reveal":
            return False

        chains = await db.get_room_chains(room_id)
        new_index = room["reveal_chain_index"] + 1

        if new_index >= len(chains):
            await db.update_room(room_id, phase="finished")
            logger.info(f"GAME FINISHED | room={room_id}")
            return False

        await db.update_room(room_id, reveal_chain_index=new_index)
        logger.debug(
            f"REVEAL ADVANCED | room={room_id} chain={new_index + 1}/{len(chains)}"
        )
        return True

    async def restart_game(self, room_id: str, host_name: str = "") -> bool:
        """Reset the room for a new game."""
        # Delete all chains (cascades to turns)
        await db.delete_room_chains(room_id)

        # Reset room state
        await db.update_room(
            room_id, phase="lobby", reveal_chain_index=0, current_turn_start=0
        )

        # Clear custom prompt from settings
        room = await db.get_room(room_id)
        if room:
            settings = room["settings"]
            settings["custom_prompt"] = ""
            await db.update_room(room_id, settings=settings)

        # Clear player chain assignments
        players = await db.get_room_players(room_id)
        for player_id in players:
            await db.update_player(player_id, current_chain_id=None)

        logger.info(f"GAME RESTARTED | room={room_id} host={host_name}")

        return True

    async def disconnect_player(self, room_id: str, player_id: str):
        """Mark a player as disconnected (for reconnection support)."""
        player = await db.get_player(player_id)
        if player:
            await db.update_player(player_id, is_connected=False, last_seen=time.time())
            logger.debug(
                f"PLAYER DISCONNECTED | room={room_id} player={player['name']} "
                f"id={player_id[:8]}..."
            )

    async def reconnect_player(self, room_id: str, player_id: str) -> bool:
        """Attempt to reconnect a player."""
        player = await db.get_player(player_id)
        if not player or player["room_id"] != room_id.upper():
            return False

        await db.update_player(player_id, is_connected=True, last_seen=time.time())
        logger.debug(
            f"PLAYER RECONNECTED (WS) | room={room_id} player={player['name']} "
            f"id={player_id[:8]}..."
        )
        return True


# Global game manager instance
game_manager = GameManager()

"""Data models for the Telemess game."""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GamePhase(str, Enum):
    """Current phase of the game."""

    LOBBY = "lobby"
    PLAYING = "playing"
    REVEAL = "reveal"
    FINISHED = "finished"


class TurnType(str, Enum):
    """Type of turn in the game chain."""

    PROMPT = "prompt"  # Initial text prompt
    DRAWING = "drawing"  # Player draws based on text
    DESCRIPTION = "description"  # Player describes what they see


@dataclass
class Turn:
    """A single turn in a game chain."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turn_type: TurnType = TurnType.PROMPT
    player_id: str = ""
    player_name: str = ""
    content: str = ""  # Text for prompt/description, base64 data URL for drawing
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "turn_type": self.turn_type.value,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class GameChain:
    """A chain of turns in the game (one complete telephone sequence)."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turns: list[Turn] = field(default_factory=list)
    current_player_index: int = 0
    player_order: list[str] = field(default_factory=list)  # Player IDs in order
    is_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "turns": [t.to_dict() for t in self.turns],
            "current_player_index": self.current_player_index,
            "player_order": self.player_order,
            "is_complete": self.is_complete,
        }


@dataclass
class Player:
    """A player in the game."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    is_host: bool = False
    is_connected: bool = True
    last_seen: float = field(default_factory=time.time)
    current_chain_id: str | None = None  # Which chain they're currently working on

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_host": self.is_host,
            "is_connected": self.is_connected,
            "last_seen": self.last_seen,
            "current_chain_id": self.current_chain_id,
        }


@dataclass
class GameSettings:
    """Settings for a game room."""

    draw_time: int = 60  # Seconds for drawing
    describe_time: int = 30  # Seconds for describing
    custom_prompt: str = ""  # Optional custom starting prompt
    max_prompt_length: int = 50  # Max chars for prompts/descriptions
    rush_warning_time: int = 10  # Seconds before end to show warning

    def to_dict(self) -> dict[str, Any]:
        return {
            "draw_time": self.draw_time,
            "describe_time": self.describe_time,
            "custom_prompt": self.custom_prompt,
            "max_prompt_length": self.max_prompt_length,
            "rush_warning_time": self.rush_warning_time,
        }


@dataclass
class Room:
    """A game room/lobby."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    name: str = ""
    players: dict[str, Player] = field(default_factory=dict)
    phase: GamePhase = GamePhase.LOBBY
    chains: list[GameChain] = field(default_factory=list)
    settings: GameSettings = field(default_factory=GameSettings)
    created_at: float = field(default_factory=time.time)
    current_turn_start: float = 0  # When the current turn started
    reveal_chain_index: int = 0  # Which chain is being revealed

    def get_host(self) -> Player | None:
        """Get the current host player."""
        for player in self.players.values():
            if player.is_host:
                return player
        return None

    def get_connected_players(self) -> list[Player]:
        """Get all connected players."""
        return [p for p in self.players.values() if p.is_connected]

    def to_dict(self, include_chains: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.name,
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "phase": self.phase.value,
            "settings": self.settings.to_dict(),
            "created_at": self.created_at,
            "current_turn_start": self.current_turn_start,
            "player_count": len(self.players),
            "connected_count": len(self.get_connected_players()),
        }
        if include_chains:
            result["chains"] = [c.to_dict() for c in self.chains]
            result["reveal_chain_index"] = self.reveal_chain_index
        return result

    def to_lobby_preview(self) -> dict[str, Any]:
        """Return minimal info for lobby list."""
        host = self.get_host()
        return {
            "id": self.id,
            "name": self.name,
            "host_name": host.name if host else "Unknown",
            "player_count": len(self.players),
            "max_players": 16,
            "phase": self.phase.value,
        }

"""SQLite database layer for Telemess game persistence."""

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

# Database file location (in the project root)
DB_PATH = Path(__file__).resolve().parent.parent.parent / "telemess.db"

# Schema version for migrations
SCHEMA_VERSION = 1


async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")

        # Create rooms table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'lobby',
                settings TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                current_turn_start REAL DEFAULT 0,
                reveal_chain_index INTEGER DEFAULT 0
            )
        """)

        # Create players table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                name TEXT NOT NULL,
                is_host INTEGER NOT NULL DEFAULT 0,
                is_connected INTEGER NOT NULL DEFAULT 1,
                last_seen REAL NOT NULL,
                current_chain_id TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
            )
        """)

        # Create chains table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chains (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                player_order TEXT NOT NULL DEFAULT '[]',
                current_player_index INTEGER NOT NULL DEFAULT 0,
                is_complete INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
            )
        """)

        # Create turns table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                chain_id TEXT NOT NULL,
                turn_type TEXT NOT NULL,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (chain_id) REFERENCES chains(id) ON DELETE CASCADE
            )
        """)

        # Create indexes for common queries
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_players_room ON players(room_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chains_room ON chains(room_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_turns_chain ON turns(chain_id)"
        )

        # Schema version tracking
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

        # Insert or update schema version
        await db.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )

        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


# =============================================================================
# ROOM OPERATIONS
# =============================================================================


async def create_room(
    room_id: str, name: str, settings: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a new room."""
    now = time.time()
    settings = settings or {}

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO rooms (id, name, phase, settings, created_at)
            VALUES (?, ?, 'lobby', ?, ?)
            """,
            (room_id, name, json.dumps(settings), now),
        )
        await db.commit()

    return {
        "id": room_id,
        "name": name,
        "phase": "lobby",
        "settings": settings,
        "created_at": now,
        "current_turn_start": 0,
        "reveal_chain_index": 0,
    }


async def get_room(room_id: str) -> dict[str, Any] | None:
    """Get a room by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rooms WHERE id = ?", (room_id.upper(),)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "phase": row["phase"],
                "settings": json.loads(row["settings"]),
                "created_at": row["created_at"],
                "current_turn_start": row["current_turn_start"],
                "reveal_chain_index": row["reveal_chain_index"],
            }


async def get_available_rooms() -> list[dict[str, Any]]:
    """Get list of joinable rooms (in lobby phase, not full)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT r.id, r.name, r.phase,
                   (SELECT COUNT(*) FROM players WHERE room_id = r.id) as player_count,
                   (SELECT name FROM players WHERE room_id = r.id AND is_host = 1 LIMIT 1) as host_name
            FROM rooms r
            WHERE r.phase = 'lobby'
              AND (SELECT COUNT(*) FROM players WHERE room_id = r.id) < 16
        """) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "host_name": row["host_name"] or "Unknown",
                    "player_count": row["player_count"],
                    "max_players": 16,
                    "phase": row["phase"],
                }
                for row in rows
            ]


async def update_room(room_id: str, **kwargs) -> bool:
    """Update room fields."""
    if not kwargs:
        return False

    # Handle settings specially (needs JSON encoding)
    if "settings" in kwargs:
        kwargs["settings"] = json.dumps(kwargs["settings"])

    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [room_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE rooms SET {fields} WHERE id = ?", values)
        await db.commit()
        return db.total_changes > 0


async def delete_room(room_id: str) -> bool:
    """Delete a room and all related data (cascades)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        await db.commit()
        return db.total_changes > 0


# =============================================================================
# PLAYER OPERATIONS
# =============================================================================


async def create_player(
    player_id: str, room_id: str, name: str, is_host: bool = False
) -> dict[str, Any]:
    """Create a new player in a room."""
    now = time.time()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO players (id, room_id, name, is_host, is_connected, last_seen)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (player_id, room_id, name, 1 if is_host else 0, now),
        )
        await db.commit()

    return {
        "id": player_id,
        "room_id": room_id,
        "name": name,
        "is_host": is_host,
        "is_connected": True,
        "last_seen": now,
        "current_chain_id": None,
    }


async def get_player(player_id: str) -> dict[str, Any] | None:
    """Get a player by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_player(row)


async def get_room_players(room_id: str) -> dict[str, dict[str, Any]]:
    """Get all players in a room as a dict keyed by player ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE room_id = ?", (room_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["id"]: _row_to_player(row) for row in rows}


async def update_player(player_id: str, **kwargs) -> bool:
    """Update player fields."""
    if not kwargs:
        return False

    # Convert boolean fields
    for key in ["is_host", "is_connected"]:
        if key in kwargs:
            kwargs[key] = 1 if kwargs[key] else 0

    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [player_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE players SET {fields} WHERE id = ?", values)
        await db.commit()
        return db.total_changes > 0


async def delete_player(player_id: str) -> bool:
    """Delete a player."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM players WHERE id = ?", (player_id,))
        await db.commit()
        return db.total_changes > 0


async def get_room_host(room_id: str) -> dict[str, Any] | None:
    """Get the host player of a room."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE room_id = ? AND is_host = 1 LIMIT 1",
            (room_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_player(row)


async def get_connected_players(room_id: str) -> list[dict[str, Any]]:
    """Get all connected players in a room."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE room_id = ? AND is_connected = 1", (room_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_player(row) for row in rows]


async def count_room_players(room_id: str) -> int:
    """Count players in a room."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM players WHERE room_id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


def _row_to_player(row: aiosqlite.Row) -> dict[str, Any]:
    """Convert a database row to a player dict."""
    return {
        "id": row["id"],
        "room_id": row["room_id"],
        "name": row["name"],
        "is_host": bool(row["is_host"]),
        "is_connected": bool(row["is_connected"]),
        "last_seen": row["last_seen"],
        "current_chain_id": row["current_chain_id"],
    }


# =============================================================================
# CHAIN OPERATIONS
# =============================================================================


async def create_chain(
    chain_id: str, room_id: str, player_order: list[str]
) -> dict[str, Any]:
    """Create a new game chain."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO chains (id, room_id, player_order, current_player_index, is_complete)
            VALUES (?, ?, ?, 0, 0)
            """,
            (chain_id, room_id, json.dumps(player_order)),
        )
        await db.commit()

    return {
        "id": chain_id,
        "room_id": room_id,
        "player_order": player_order,
        "current_player_index": 0,
        "is_complete": False,
    }


async def get_chain(chain_id: str) -> dict[str, Any] | None:
    """Get a chain by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM chains WHERE id = ?", (chain_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_chain(row)


async def get_room_chains(room_id: str) -> list[dict[str, Any]]:
    """Get all chains in a room with their turns."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Get chains
        async with db.execute(
            "SELECT * FROM chains WHERE room_id = ?", (room_id,)
        ) as cursor:
            chain_rows = await cursor.fetchall()

        chains = []
        for chain_row in chain_rows:
            chain = _row_to_chain(chain_row)

            # Get turns for this chain
            async with db.execute(
                "SELECT * FROM turns WHERE chain_id = ? ORDER BY position",
                (chain["id"],),
            ) as cursor:
                turn_rows = await cursor.fetchall()
                chain["turns"] = [_row_to_turn(row) for row in turn_rows]

            chains.append(chain)

        return chains


async def update_chain(chain_id: str, **kwargs) -> bool:
    """Update chain fields."""
    if not kwargs:
        return False

    # Handle special fields
    if "player_order" in kwargs:
        kwargs["player_order"] = json.dumps(kwargs["player_order"])
    if "is_complete" in kwargs:
        kwargs["is_complete"] = 1 if kwargs["is_complete"] else 0

    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [chain_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE chains SET {fields} WHERE id = ?", values)
        await db.commit()
        return db.total_changes > 0


async def delete_room_chains(room_id: str) -> bool:
    """Delete all chains in a room."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM chains WHERE room_id = ?", (room_id,))
        await db.commit()
        return db.total_changes > 0


def _row_to_chain(row: aiosqlite.Row) -> dict[str, Any]:
    """Convert a database row to a chain dict."""
    return {
        "id": row["id"],
        "room_id": row["room_id"],
        "player_order": json.loads(row["player_order"]),
        "current_player_index": row["current_player_index"],
        "is_complete": bool(row["is_complete"]),
        "turns": [],  # Will be populated separately
    }


# =============================================================================
# TURN OPERATIONS
# =============================================================================


async def create_turn(
    turn_id: str,
    chain_id: str,
    turn_type: str,
    player_id: str,
    player_name: str,
    content: str,
    position: int,
) -> dict[str, Any]:
    """Create a new turn in a chain."""
    now = time.time()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO turns (id, chain_id, turn_type, player_id, player_name, content, timestamp, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                chain_id,
                turn_type,
                player_id,
                player_name,
                content,
                now,
                position,
            ),
        )
        await db.commit()

    return {
        "id": turn_id,
        "chain_id": chain_id,
        "turn_type": turn_type,
        "player_id": player_id,
        "player_name": player_name,
        "content": content,
        "timestamp": now,
        "position": position,
    }


async def get_chain_turns(chain_id: str) -> list[dict[str, Any]]:
    """Get all turns in a chain, ordered by position."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM turns WHERE chain_id = ? ORDER BY position", (chain_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_turn(row) for row in rows]


async def get_last_turn(chain_id: str) -> dict[str, Any] | None:
    """Get the last turn in a chain."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM turns WHERE chain_id = ? ORDER BY position DESC LIMIT 1",
            (chain_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_turn(row)


async def count_chain_turns(chain_id: str) -> int:
    """Count turns in a chain."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM turns WHERE chain_id = ?", (chain_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


def _row_to_turn(row: aiosqlite.Row) -> dict[str, Any]:
    """Convert a database row to a turn dict."""
    return {
        "id": row["id"],
        "chain_id": row["chain_id"],
        "turn_type": row["turn_type"],
        "player_id": row["player_id"],
        "player_name": row["player_name"],
        "content": row["content"],
        "timestamp": row["timestamp"],
        "position": row["position"],
    }


# =============================================================================
# CLEANUP OPERATIONS
# =============================================================================


async def cleanup_stale_data(
    disconnect_timeout: int = 300, room_timeout: int = 600
) -> tuple[int, int]:
    """
    Clean up stale players and empty rooms.
    Returns (players_removed, rooms_removed).
    """
    now = time.time()
    players_removed = 0
    rooms_removed = 0

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Remove disconnected players past timeout
        cursor = await db.execute(
            """
            DELETE FROM players
            WHERE is_connected = 0 AND (? - last_seen) > ?
            """,
            (now, disconnect_timeout),
        )
        players_removed = cursor.rowcount

        # Find and delete empty rooms past timeout
        cursor = await db.execute(
            """
            DELETE FROM rooms
            WHERE id IN (
                SELECT r.id FROM rooms r
                LEFT JOIN players p ON r.id = p.room_id
                GROUP BY r.id
                HAVING COUNT(p.id) = 0 AND (? - r.created_at) > ?
            )
            """,
            (now, room_timeout),
        )
        rooms_removed = cursor.rowcount

        await db.commit()

    return players_removed, rooms_removed


async def ensure_room_has_host(room_id: str) -> str | None:
    """
    Ensure a room has a host. If not, promote a connected player.
    Returns the new host's player_id, or None if no players available.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check if there's already a connected host
        async with db.execute(
            """
            SELECT id FROM players
            WHERE room_id = ? AND is_host = 1 AND is_connected = 1
            LIMIT 1
            """,
            (room_id,),
        ) as cursor:
            if await cursor.fetchone():
                return None  # Host exists

        # Remove host status from all players in room
        await db.execute("UPDATE players SET is_host = 0 WHERE room_id = ?", (room_id,))

        # Find a connected player to promote
        async with db.execute(
            """
            SELECT id FROM players
            WHERE room_id = ? AND is_connected = 1
            ORDER BY last_seen ASC
            LIMIT 1
            """,
            (room_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            new_host_id = row["id"]

        # Promote to host
        await db.execute("UPDATE players SET is_host = 1 WHERE id = ?", (new_host_id,))

        await db.commit()
        return new_host_id

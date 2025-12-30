# 🎨 Telemess

**The drawing game where things go hilariously wrong.**

Players alternate between drawing a prompt and describing what they see. You may start with "cooking pancakes" and end with "alien disco party". The reveal at the end showing the progression is comedy gold!

![Telemess Preview](https://via.placeholder.com/600x300/FEF7E3/2D3047?text=Telemess+%F0%9F%8E%A8)

## ✨ Features

- 🎮 **Real-time multiplayer** - Up to 16 players per game
- 📱 **Mobile-first design** - Optimized for phones and tablets
- 🌙 **Dark/Light mode** - Comfortable playing any time
- 🎨 **Touch-friendly canvas** - Draw with your finger on mobile
- ⏱️ **Customizable timers** - Set your own pace
- 👑 **Host migration** - Game continues if the host leaves
- 🔄 **Player persistence** - Rejoin if you accidentally close the app
- 🎭 **Parallel chains** - Multiple games run simultaneously to keep everyone engaged
- 🎉 **Epic reveal** - Watch the hilarious transformation unfold

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

#### Windows (PowerShell)

```powershell
# One-time setup (allow local scripts)
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser

# If you get "script is not digitally signed" error:
Unblock-File -Path .\setup\windows_setup.ps1

# Run setup
.\setup\windows_setup.ps1
```

#### Linux/macOS

```bash
chmod +x setup/linux_setup.sh
./setup/linux_setup.sh
```

### Running the Game

```bash
# Using uv with uvicorn (recommended)
uv run uvicorn telemess.main:app --app-dir src --host 0.0.0.0 --port 8000

# With auto-reload for development
uv run uvicorn telemess.main:app --app-dir src --host 0.0.0.0 --port 8000 --reload

# Or activate venv first, then run uvicorn directly
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Then run:
uvicorn telemess.main:app --app-dir src --host 0.0.0.0 --port 8000
```

The game will start at **http://localhost:8000**

For network play (other devices on your network):
- Find your local IP (e.g., `192.168.1.100`)
- Players connect to `http://192.168.1.100:8000`

## 🎯 How to Play

1. **Enter your name** - This is saved for future sessions
2. **Join or host a game** - Create a room or join an existing one
3. **Wait for players** - Need at least 3 players to start
4. **Host starts the game** - Can set custom prompts and timers
5. **Draw or describe** - Alternate between drawing prompts and describing drawings
6. **Watch the reveal** - See how "cooking pancakes" became "alien disco party"!

## 🎮 Game Flow

```
Round 1: Player A sees prompt → draws it
Round 2: Player B sees drawing → describes it
Round 3: Player C sees description → draws it
Round 4: Player D sees drawing → describes it
... and so on until everyone has had a turn
```

With 14-16 players, the game runs **2-3 parallel chains** so everyone stays engaged!

## ⚙️ Host Settings

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| Drawing Time | 30-120s | 60s | Time to complete a drawing |
| Description Time | 15-60s | 30s | Time to write a description |
| Custom Prompt | 0-50 chars | Random | Starting prompt for chain 1 |

## 🖥️ Deployment on Raspberry Pi

This game is optimized for Raspberry Pi 4:

```bash
# Clone the repo
git clone <your-repo-url> telemess
cd telemess

# Run setup
chmod +x setup/linux_setup.sh
./setup/linux_setup.sh

# Run the game
uv run uvicorn telemess.main:app --app-dir src --host 0.0.0.0 --port 8000
```

For automatic startup, add to `/etc/rc.local`:

```bash
cd /home/pi/telemess && /home/pi/.local/bin/uv run uvicorn telemess.main:app --app-dir src --host 0.0.0.0 --port 8000 &
```

## 🌐 Network Configuration

For LAN play:
1. Ensure all devices are on the same network
2. Find the host's local IP: `hostname -I` (Linux) or `ipconfig` (Windows)
3. Share the URL: `http://<host-ip>:8000`

## 📁 Project Structure

```
telemess/
├── src/telemess/
│   ├── __init__.py
│   ├── main.py           # FastAPI app entry point
│   ├── models.py         # Data models
│   ├── game_manager.py   # Game state logic
│   ├── websocket_handler.py  # Real-time communication
│   ├── prompts.py        # Fun random prompts
│   └── static/
│       ├── index.html    # Main game page
│       ├── styles.css    # Mobile-first styles
│       └── app.js        # Client-side game logic
├── setup/
│   ├── windows_setup.ps1
│   └── linux_setup.sh
├── pyproject.toml
└── README.md
```

## 🔧 Development

```bash
# Install dependencies
uv sync

# Run in development mode (with auto-reload)
uv run uvicorn telemess.main:app --app-dir src --host 0.0.0.0 --port 8000 --reload

# Run linting
uv run ruff check .

# Run pre-commit hooks
uv run pre-commit run --all-files
```

## 🎨 Design Decisions

### Big Reveal vs Progressive Viewing
We chose the **big reveal at the end** because:
- The comedy builds exponentially when you see the full transformation
- Progressive viewing would spoil the "how did we get here?!" moment
- The reveal ceremony becomes a shared social experience

### Canvas in Dark Mode
Following industry standards (Figma, Excalidraw, Miro):
- The **canvas always stays white** regardless of theme
- This ensures proper contrast for drawings
- The UI around the canvas changes with the theme

### Keeping Players Engaged
With 14-16 players, we run **multiple parallel chains**:
- 2-3 chains running simultaneously
- More players active at any given time
- Waiting players see progress bars for all chains
- More content for the final reveal!

## 📝 License

MIT License - feel free to use and modify!

---

Made with ❤️ for game nights that need more chaos.

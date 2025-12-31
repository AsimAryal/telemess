/**
 * Telemess - The Drawing Game Where Things Go Hilariously Wrong
 * Client-side application
 */

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

const state = {
    playerName: localStorage.getItem('telemess_player_name') || '',
    playerId: localStorage.getItem('telemess_player_id') || '',
    roomId: localStorage.getItem('telemess_room_id') || null,
    room: null,
    ws: null,
    isHost: false,
    currentTurn: null,
    currentScreen: null,  // Track current screen to avoid re-initialization
    timerInterval: null,
    timeRemaining: 0,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,

    // Drawing state
    canvas: null,
    ctx: null,
    isDrawing: false,
    lastX: 0,
    lastY: 0,
    currentColor: '#2D3047',
    brushSize: 8,
    isEraser: false,
    drawingHistory: [],
};

// ============================================================================
// SESSION PERSISTENCE
// ============================================================================

function saveSession() {
    if (state.roomId) {
        localStorage.setItem('telemess_room_id', state.roomId);
    }
    if (state.playerId) {
        localStorage.setItem('telemess_player_id', state.playerId);
    }
}

function clearSession() {
    localStorage.removeItem('telemess_room_id');
    state.roomId = null;
    state.room = null;
    state.currentScreen = null;
    state.reconnectAttempts = 0;
}

async function tryRestoreSession() {
    // If we have a stored room ID, try to rejoin
    const storedRoomId = localStorage.getItem('telemess_room_id');
    const storedPlayerId = localStorage.getItem('telemess_player_id');

    if (!storedRoomId || !storedPlayerId || !state.playerName) {
        return false;
    }

    try {
        const result = await joinRoom(storedRoomId);
        if (result) {
            state.roomId = result.room_id;
            state.playerId = result.player_id;
            state.room = result.room;
            saveSession();
            connectWebSocket();
            return true;
        }
    } catch (e) {
        console.log('Could not restore session:', e);
    }

    // Room no longer exists, clear the stored session
    clearSession();
    return false;
}

// ============================================================================
// SCREEN MANAGEMENT
// ============================================================================

function showScreen(screenId) {
    if (state.currentScreen === screenId) {
        return false; // Already on this screen
    }

    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.remove('active');
    });
    const screen = document.getElementById(`screen-${screenId}`);
    if (screen) {
        screen.classList.add('active');
    }
    state.currentScreen = screenId;
    return true; // Screen changed
}

// ============================================================================
// THEME MANAGEMENT
// ============================================================================

function initTheme() {
    const savedTheme = localStorage.getItem('telemess_theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeColor(savedTheme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('telemess_theme', next);
    updateThemeColor(next);
}

function updateThemeColor(theme) {
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    metaThemeColor.content = theme === 'dark' ? '#1A1B2E' : '#FEF7E3';
}

// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ============================================================================
// API CALLS
// ============================================================================

async function fetchRooms() {
    try {
        const res = await fetch('/api/rooms');
        return await res.json();
    } catch (e) {
        console.error('Failed to fetch rooms:', e);
        return [];
    }
}

async function createRoom(roomName) {
    try {
        const res = await fetch('/api/rooms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                host_name: state.playerName,
                room_name: roomName,
            }),
        });
        return await res.json();
    } catch (e) {
        console.error('Failed to create room:', e);
        showToast('Failed to create room', 'error');
        return null;
    }
}

async function joinRoom(roomId) {
    try {
        const res = await fetch(`/api/rooms/${roomId}/join`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                player_name: state.playerName,
                player_id: state.playerId || undefined,
            }),
        });
        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || 'Failed to join room', 'error');
            return null;
        }
        return await res.json();
    } catch (e) {
        console.error('Failed to join room:', e);
        showToast('Failed to join room', 'error');
        return null;
    }
}

// ============================================================================
// WEBSOCKET CONNECTION
// ============================================================================

function connectWebSocket() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        return; // Already connected
    }

    if (state.ws) {
        state.ws.close();
    }

    if (!state.roomId || !state.playerId) {
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${state.roomId}/${state.playerId}`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        console.log('WebSocket connected');
        state.reconnectAttempts = 0; // Reset on successful connection
        // Request current state
        state.ws.send(JSON.stringify({ type: 'get_state' }));
    };

    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };

    state.ws.onclose = () => {
        console.log('WebSocket disconnected');
        scheduleReconnect();
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function scheduleReconnect() {
    // Don't reconnect if we've explicitly left or have no room
    if (!state.roomId || !state.playerId) {
        return;
    }

    state.reconnectAttempts++;

    if (state.reconnectAttempts > state.maxReconnectAttempts) {
        console.log('Max reconnect attempts reached');
        showToast('Connection lost. Please rejoin the room.', 'error');
        clearSession();
        showScreen('lobby-browser');
        refreshRoomList();
        return;
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s
    const delay = Math.min(1000 * Math.pow(2, state.reconnectAttempts - 1), 16000);
    console.log(`Reconnecting in ${delay}ms (attempt ${state.reconnectAttempts})`);

    setTimeout(() => {
        if (state.roomId && state.playerId) {
            connectWebSocket();
        }
    }, delay);
}

function handleVisibilityChange() {
    if (document.visibilityState === 'visible') {
        // Tab/app became visible - check if we need to reconnect
        if (state.roomId && state.playerId) {
            if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
                console.log('Reconnecting after visibility change');
                state.reconnectAttempts = 0; // Reset attempts on manual visibility
                connectWebSocket();
            } else {
                // Already connected, just request fresh state
                sendMessage({ type: 'get_state' });
            }
        }
    }
}

function sendMessage(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(data));
    }
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'game_state':
            handleGameState(data);
            break;
        case 'turn_info':
            handleTurnInfo(data.turn_info);
            break;
        case 'timer_sync':
            // Lightweight timer sync - just update the timer without re-rendering
            handleTimerSync(data);
            break;
        case 'player_connected':
        case 'player_disconnected':
            if (data.room) {
                state.room = data.room;
                updateLobbyUI();
            }
            break;
        case 'game_finished':
            showScreen('finished');
            break;
        case 'error':
            showToast(data.message, 'error');
            break;
        case 'pong':
            // Keep-alive response
            break;
    }
}

function handleTimerSync(data) {
    // Only sync if we have an active turn
    if (!state.currentTurn || !state.currentTurn.is_your_turn) return;

    const timeLimit = state.currentTurn.turn_type === 'drawing'
        ? state.currentTurn.time_limit
        : state.currentTurn.time_limit;

    const newTimeRemaining = Math.max(0, Math.ceil(timeLimit - data.elapsed));

    // Only update if significantly different (more than 2 seconds drift)
    if (Math.abs(state.timeRemaining - newTimeRemaining) > 2) {
        state.timeRemaining = newTimeRemaining;
    }
}

function handleGameState(data) {
    state.room = data.room;
    state.playerId = data.your_id;

    // Persist player ID
    localStorage.setItem('telemess_player_id', state.playerId);

    const player = state.room.players[state.playerId];
    state.isHost = player?.is_host || false;

    switch (state.room.phase) {
        case 'lobby':
            // Reset current screen when going to lobby (new game)
            state.currentScreen = null;
            showScreen('lobby');
            updateLobbyUI();
            break;
        case 'playing':
            if (data.turn_info) {
                handleTurnInfo(data.turn_info);
            }
            break;
        case 'reveal':
            showScreen('reveal');
            updateRevealUI();
            break;
        case 'finished':
            showScreen('finished');
            break;
    }
}

function handleTurnInfo(turnInfo) {
    state.currentTurn = turnInfo;

    if (turnInfo.is_your_turn) {
        if (turnInfo.turn_type === 'drawing') {
            const screenChanged = showScreen('draw');
            if (screenChanged) {
                setupDrawingScreen();
                startTimer();
            }
        } else {
            const screenChanged = showScreen('describe');
            if (screenChanged) {
                setupDescribeScreen();
                startTimer();
            }
        }
    } else {
        showScreen('waiting');
        updateWaitingUI();
    }
}

// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

function updateLobbyUI() {
    const room = state.room;
    if (!room) return;

    document.getElementById('lobby-room-name').textContent = room.name;
    document.getElementById('lobby-room-code').textContent = room.id;
    document.getElementById('player-count').textContent = Object.keys(room.players).length;

    // Update player list
    const playerList = document.getElementById('lobby-player-list');
    playerList.innerHTML = '';

    Object.values(room.players).forEach(player => {
        const chip = document.createElement('div');
        chip.className = 'player-chip';
        if (player.is_host) chip.classList.add('host');
        if (player.id === state.playerId) chip.classList.add('you');
        if (!player.is_connected) chip.classList.add('disconnected');

        const initial = player.name.charAt(0).toUpperCase();
        chip.innerHTML = `
            <span class="player-avatar">${initial}</span>
            <span>${player.name}${player.is_host ? ' (host)' : ''}${player.id === state.playerId ? ' (you)' : ''}</span>
        `;
        playerList.appendChild(chip);
    });

    // Show/hide host controls
    const hostSettings = document.getElementById('host-settings');
    const startBtn = document.getElementById('btn-start-game');
    const waitingMsg = document.getElementById('waiting-for-host');

    if (state.isHost) {
        hostSettings.classList.remove('hidden');
        startBtn.classList.remove('hidden');
        waitingMsg.classList.add('hidden');

        // Update settings inputs
        document.getElementById('setting-draw-time').value = room.settings.draw_time;
        document.getElementById('draw-time-value').textContent = `${room.settings.draw_time}s`;
        document.getElementById('setting-describe-time').value = room.settings.describe_time;
        document.getElementById('describe-time-value').textContent = `${room.settings.describe_time}s`;
        document.getElementById('setting-custom-prompt').value = room.settings.custom_prompt || '';

        // Enable/disable start button
        const playerCount = Object.keys(room.players).length;
        startBtn.disabled = playerCount < 3;
        if (playerCount < 3) {
            startBtn.textContent = `Need ${3 - playerCount} more players`;
        } else {
            startBtn.textContent = 'Start Game!';
        }
    } else {
        hostSettings.classList.add('hidden');
        startBtn.classList.add('hidden');
        waitingMsg.classList.remove('hidden');
    }
}

function updateWaitingUI() {
    const progress = state.currentTurn?.chains_progress || [];
    const container = document.getElementById('chains-progress');
    container.innerHTML = '';

    progress.forEach((chain, i) => {
        const percent = chain.total_players > 0
            ? Math.round((chain.turns_complete / (chain.total_players + 1)) * 100)
            : 0;

        const div = document.createElement('div');
        div.className = 'chain-progress';
        div.innerHTML = `
            <div class="chain-progress-header">
                <span>Chain ${chain.chain_number}</span>
                <span>${chain.is_complete ? 'Complete' : `${chain.turns_complete}/${chain.total_players + 1}`}</span>
            </div>
            <div class="chain-progress-bar">
                <div class="chain-progress-fill" style="width: ${percent}%"></div>
            </div>
        `;
        container.appendChild(div);
    });
}

function updateRevealUI() {
    if (!state.room || !state.room.chains) return;

    const chains = state.room.chains;
    const currentIndex = state.room.reveal_chain_index || 0;
    const chain = chains[currentIndex];

    document.getElementById('reveal-chain-num').textContent = currentIndex + 1;
    document.getElementById('reveal-total-chains').textContent = chains.length;

    // Update dots
    const dotsContainer = document.getElementById('reveal-dots');
    dotsContainer.innerHTML = '';
    chains.forEach((_, i) => {
        const dot = document.createElement('div');
        dot.className = `reveal-dot ${i === currentIndex ? 'active' : ''}`;
        dotsContainer.appendChild(dot);
    });

    // Show chain turns with staggered animation
    const chainContainer = document.getElementById('reveal-chain');
    chainContainer.innerHTML = '';

    if (chain && chain.turns) {
        chain.turns.forEach((turn, i) => {
            const turnDiv = document.createElement('div');
            turnDiv.className = 'reveal-turn';
            turnDiv.style.animationDelay = `${i * 0.3}s`;

            let contentHtml = '';
            if (turn.turn_type === 'drawing') {
                contentHtml = `<img src="${turn.content}" alt="Drawing" class="reveal-image">`;
            } else {
                contentHtml = `<div class="reveal-content">"${turn.content}"</div>`;
            }

            const typeLabels = {
                prompt: 'Starting Prompt',
                drawing: 'Drew',
                description: 'Described as'
            };

            turnDiv.innerHTML = `
                <div class="reveal-player">${turn.player_name}</div>
                <div class="reveal-type">${typeLabels[turn.turn_type] || turn.turn_type}</div>
                ${contentHtml}
            `;
            chainContainer.appendChild(turnDiv);
        });
    }

    // Update next button
    const nextBtn = document.getElementById('btn-reveal-next');
    if (currentIndex >= chains.length - 1) {
        nextBtn.textContent = 'Finish';
    } else {
        nextBtn.textContent = 'Next Chain →';
    }

    // Only host can advance
    nextBtn.style.display = state.isHost ? 'block' : 'none';
}

// ============================================================================
// TIMER
// ============================================================================

function startTimer() {
    clearInterval(state.timerInterval);

    if (!state.currentTurn) return;

    state.timeRemaining = Math.ceil(state.currentTurn.time_remaining);
    const timerEl = state.currentTurn.turn_type === 'drawing'
        ? document.getElementById('draw-timer')
        : document.getElementById('describe-timer');

    const rushOverlay = document.getElementById('rush-overlay');
    const rushTime = state.currentTurn.rush_warning_time || 10;

    updateTimerDisplay(timerEl, rushOverlay, rushTime);

    state.timerInterval = setInterval(() => {
        state.timeRemaining = Math.max(0, state.timeRemaining - 1);
        updateTimerDisplay(timerEl, rushOverlay, rushTime);

        if (state.timeRemaining <= 0) {
            clearInterval(state.timerInterval);
            // Auto-submit if time runs out
            if (state.currentTurn.turn_type === 'drawing') {
                submitDrawing();
            } else {
                submitDescription();
            }
        }
    }, 1000);
}

function updateTimerDisplay(timerEl, rushOverlay, rushTime) {
    if (!timerEl) return;

    timerEl.textContent = state.timeRemaining;

    if (state.timeRemaining <= rushTime) {
        timerEl.classList.add('warning');
        rushOverlay.classList.add('active');
    } else {
        timerEl.classList.remove('warning');
        rushOverlay.classList.remove('active');
    }
}

// ============================================================================
// DRAWING CANVAS
// ============================================================================

function setupDrawingScreen() {
    const turn = state.currentTurn;
    if (!turn) return;

    document.getElementById('draw-prompt').textContent = turn.previous_content;
    initCanvas();
}

function initCanvas() {
    state.canvas = document.getElementById('drawing-canvas');
    state.ctx = state.canvas.getContext('2d');

    // Set canvas size based on container
    const container = state.canvas.parentElement;
    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    state.canvas.width = rect.width * dpr;
    state.canvas.height = (rect.width * 0.75) * dpr; // 4:3 aspect ratio
    state.canvas.style.width = `${rect.width}px`;
    state.canvas.style.height = `${rect.width * 0.75}px`;

    state.ctx.scale(dpr, dpr);

    // Clear canvas with white background (use CSS pixel dimensions after scaling)
    state.ctx.fillStyle = '#FFFFFF';
    state.ctx.fillRect(0, 0, state.canvas.width / dpr, state.canvas.height / dpr);

    // Reset drawing state
    state.drawingHistory = [];
    state.isEraser = false;
    document.getElementById('btn-eraser').classList.remove('active');

    // Save initial state
    saveDrawingState();

    // Set up event listeners
    setupCanvasEvents();
}

function setupCanvasEvents() {
    const canvas = state.canvas;

    // Mouse events
    canvas.addEventListener('mousedown', startDrawing);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDrawing);
    canvas.addEventListener('mouseout', stopDrawing);

    // Touch events
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', stopDrawing);
    canvas.addEventListener('touchcancel', stopDrawing);
}

function getCanvasCoords(e) {
    const rect = state.canvas.getBoundingClientRect();

    if (e.touches && e.touches.length > 0) {
        return {
            x: e.touches[0].clientX - rect.left,
            y: e.touches[0].clientY - rect.top
        };
    }

    return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
}

function handleTouchStart(e) {
    e.preventDefault();
    startDrawing(e);
}

function handleTouchMove(e) {
    e.preventDefault();
    draw(e);
}

function startDrawing(e) {
    state.isDrawing = true;
    const coords = getCanvasCoords(e);
    state.lastX = coords.x;
    state.lastY = coords.y;

    // Draw a dot for single clicks/taps
    state.ctx.beginPath();
    state.ctx.arc(coords.x, coords.y, state.brushSize / 2, 0, Math.PI * 2);
    state.ctx.fillStyle = state.isEraser ? '#FFFFFF' : state.currentColor;
    state.ctx.fill();
}

function draw(e) {
    if (!state.isDrawing) return;

    const coords = getCanvasCoords(e);

    state.ctx.beginPath();
    state.ctx.moveTo(state.lastX, state.lastY);
    state.ctx.lineTo(coords.x, coords.y);
    state.ctx.strokeStyle = state.isEraser ? '#FFFFFF' : state.currentColor;
    state.ctx.lineWidth = state.brushSize;
    state.ctx.lineCap = 'round';
    state.ctx.lineJoin = 'round';
    state.ctx.stroke();

    state.lastX = coords.x;
    state.lastY = coords.y;
}

function stopDrawing() {
    if (state.isDrawing) {
        state.isDrawing = false;
        saveDrawingState();
    }
}

function saveDrawingState() {
    if (!state.canvas) return;
    const imageData = state.canvas.toDataURL('image/png');
    state.drawingHistory.push(imageData);
    // Limit history size
    if (state.drawingHistory.length > 20) {
        state.drawingHistory.shift();
    }
}

function undoDrawing() {
    if (state.drawingHistory.length > 1) {
        state.drawingHistory.pop(); // Remove current state
        const previousState = state.drawingHistory[state.drawingHistory.length - 1];

        const img = new Image();
        img.onload = () => {
            state.ctx.clearRect(0, 0, state.canvas.width, state.canvas.height);
            state.ctx.drawImage(img, 0, 0, state.canvas.width / (window.devicePixelRatio || 1), state.canvas.height / (window.devicePixelRatio || 1));
        };
        img.src = previousState;
    }
}

function clearCanvas() {
    if (!state.ctx || !state.canvas) return;
    const dpr = window.devicePixelRatio || 1;
    state.ctx.fillStyle = '#FFFFFF';
    state.ctx.fillRect(0, 0, state.canvas.width / dpr, state.canvas.height / dpr);
    saveDrawingState();
}

function submitDrawing() {
    clearInterval(state.timerInterval);
    document.getElementById('rush-overlay').classList.remove('active');

    if (!state.canvas || !state.currentTurn) return;

    const imageData = state.canvas.toDataURL('image/png');

    sendMessage({
        type: 'submit_turn',
        chain_id: state.currentTurn.chain_id,
        content: imageData,
    });
}

// ============================================================================
// DESCRIPTION INPUT
// ============================================================================

function setupDescribeScreen() {
    const turn = state.currentTurn;
    if (!turn) return;

    document.getElementById('describe-image').src = turn.previous_content || '';
    document.getElementById('input-description').value = '';
    document.getElementById('char-counter').textContent = '0/50';
    document.getElementById('char-counter').classList.remove('limit');
}

function submitDescription() {
    clearInterval(state.timerInterval);
    document.getElementById('rush-overlay').classList.remove('active');

    if (!state.currentTurn) return;

    const description = document.getElementById('input-description').value.trim();
    if (!description) {
        showToast('Please enter a description', 'error');
        return;
    }

    sendMessage({
        type: 'submit_turn',
        chain_id: state.currentTurn.chain_id,
        content: description,
    });
}

// ============================================================================
// ROOM LIST
// ============================================================================

async function refreshRoomList() {
    const rooms = await fetchRooms();
    const container = document.getElementById('room-list');

    if (rooms.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">—</div>
                <p>No games available</p>
                <p class="text-muted">Be the first to host one!</p>
            </div>
        `;
        return;
    }

    container.innerHTML = '';
    rooms.forEach(room => {
        const item = document.createElement('div');
        item.className = 'room-item';
        item.innerHTML = `
            <div class="room-info">
                <div class="room-name">${room.name}</div>
                <div class="room-host">Hosted by ${room.host_name}</div>
            </div>
            <div class="room-players">
                <span>${room.player_count}/16</span>
            </div>
        `;
        item.addEventListener('click', () => handleJoinRoom(room.id));
        container.appendChild(item);
    });
}

// ============================================================================
// EVENT HANDLERS
// ============================================================================

async function handleSaveName() {
    const input = document.getElementById('input-name');
    const name = input.value.trim();

    if (!name) {
        showToast('Please enter your name', 'error');
        return;
    }

    state.playerName = name;
    localStorage.setItem('telemess_player_name', name);

    showScreen('lobby-browser');
    refreshRoomList();
}

async function handleCreateRoom() {
    const roomName = document.getElementById('input-room-name').value.trim();
    const result = await createRoom(roomName);

    if (result) {
        state.roomId = result.room_id;
        state.playerId = result.player_id;
        state.room = result.room;
        state.isHost = true;
        state.reconnectAttempts = 0;

        saveSession();
        connectWebSocket();
        showScreen('lobby');
        updateLobbyUI();
        showToast('Room created!', 'success');
    }
}

async function handleJoinRoom(roomId) {
    const result = await joinRoom(roomId);

    if (result) {
        state.roomId = result.room_id;
        state.playerId = result.player_id;
        state.room = result.room;
        state.reconnectAttempts = 0;

        saveSession();
        connectWebSocket();
        showScreen('lobby');
        updateLobbyUI();
        showToast('Joined room!', 'success');
    }
}

async function handleQuickJoin() {
    const code = document.getElementById('input-room-code').value.trim().toUpperCase();
    if (!code) {
        showToast('Please enter a room code', 'error');
        return;
    }
    await handleJoinRoom(code);
}

function handleLeaveLobby() {
    sendMessage({ type: 'leave' });
    clearSession();
    state.ws?.close();
    state.ws = null;
    showScreen('lobby-browser');
    refreshRoomList();
}

function handleStartGame() {
    sendMessage({ type: 'start_game' });
}

function handleUpdateSettings() {
    const settings = {
        draw_time: parseInt(document.getElementById('setting-draw-time').value),
        describe_time: parseInt(document.getElementById('setting-describe-time').value),
        custom_prompt: document.getElementById('setting-custom-prompt').value.trim(),
    };
    sendMessage({ type: 'update_settings', settings });
}

function handleRevealNext() {
    sendMessage({ type: 'advance_reveal' });
}

function handlePlayAgain() {
    sendMessage({ type: 'restart_game' });
}

function handleBackToLobby() {
    sendMessage({ type: 'leave' });
    clearSession();
    state.ws?.close();
    state.ws = null;
    showScreen('lobby-browser');
    refreshRoomList();
}

// ============================================================================
// INITIALIZATION
// ============================================================================

function initEventListeners() {
    // Theme toggle
    document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

    // Name entry
    document.getElementById('btn-save-name').addEventListener('click', handleSaveName);
    document.getElementById('input-name').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSaveName();
    });

    // Tabs
    document.getElementById('tab-join').addEventListener('click', () => {
        document.getElementById('tab-join').classList.add('active');
        document.getElementById('tab-host').classList.remove('active');
        document.getElementById('tab-content-join').classList.remove('hidden');
        document.getElementById('tab-content-host').classList.add('hidden');
    });
    document.getElementById('tab-host').addEventListener('click', () => {
        document.getElementById('tab-host').classList.add('active');
        document.getElementById('tab-join').classList.remove('active');
        document.getElementById('tab-content-host').classList.remove('hidden');
        document.getElementById('tab-content-join').classList.add('hidden');
    });

    // Room list
    document.getElementById('btn-refresh-rooms').addEventListener('click', refreshRoomList);
    document.getElementById('btn-quick-join').addEventListener('click', handleQuickJoin);
    document.getElementById('btn-create-room').addEventListener('click', handleCreateRoom);

    // Lobby
    document.getElementById('btn-leave-lobby').addEventListener('click', handleLeaveLobby);
    document.getElementById('btn-start-game').addEventListener('click', handleStartGame);

    // Settings
    document.getElementById('setting-draw-time').addEventListener('input', (e) => {
        document.getElementById('draw-time-value').textContent = `${e.target.value}s`;
        handleUpdateSettings();
    });
    document.getElementById('setting-describe-time').addEventListener('input', (e) => {
        document.getElementById('describe-time-value').textContent = `${e.target.value}s`;
        handleUpdateSettings();
    });
    document.getElementById('setting-custom-prompt').addEventListener('change', handleUpdateSettings);

    // Drawing tools
    document.getElementById('color-picker').addEventListener('click', (e) => {
        const btn = e.target.closest('.color-btn');
        if (!btn) return;
        document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.currentColor = btn.dataset.color;
        state.isEraser = false;
        document.getElementById('btn-eraser').classList.remove('active');
    });

    document.getElementById('brush-sizes').addEventListener('click', (e) => {
        const btn = e.target.closest('.brush-btn');
        if (!btn) return;
        document.querySelectorAll('.brush-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.brushSize = parseInt(btn.dataset.size);
    });

    document.getElementById('btn-eraser').addEventListener('click', () => {
        state.isEraser = !state.isEraser;
        document.getElementById('btn-eraser').classList.toggle('active', state.isEraser);
    });

    document.getElementById('btn-clear').addEventListener('click', clearCanvas);
    document.getElementById('btn-undo').addEventListener('click', undoDrawing);
    document.getElementById('btn-submit-drawing').addEventListener('click', submitDrawing);

    // Description
    document.getElementById('input-description').addEventListener('input', (e) => {
        const len = e.target.value.length;
        const counter = document.getElementById('char-counter');
        counter.textContent = `${len}/50`;
        counter.classList.toggle('limit', len >= 45);
    });
    document.getElementById('input-description').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitDescription();
    });
    document.getElementById('btn-submit-description').addEventListener('click', submitDescription);

    // Reveal
    document.getElementById('btn-reveal-next').addEventListener('click', handleRevealNext);
    document.getElementById('btn-reveal-main-menu').addEventListener('click', handleBackToLobby);

    // Finished
    document.getElementById('btn-play-again').addEventListener('click', handlePlayAgain);
    document.getElementById('btn-back-to-lobby').addEventListener('click', handleBackToLobby);

    // Keep-alive ping
    setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            sendMessage({ type: 'ping' });
        }
    }, 30000);
}

async function init() {
    initTheme();
    initEventListeners();

    // Add visibility change listener for mobile app switching
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Check if player has a name saved
    if (!state.playerName) {
        showScreen('name');
        return;
    }

    document.getElementById('input-name').value = state.playerName;

    // Try to restore previous session (rejoin room if we were in one)
    if (state.roomId) {
        showToast('Reconnecting to game...', 'info');
        const restored = await tryRestoreSession();
        if (restored) {
            // Session restored, WebSocket will handle showing the right screen
            return;
        }
    }

    // No session to restore, show lobby browser
    showScreen('lobby-browser');
    refreshRoomList();
}

// Start the app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

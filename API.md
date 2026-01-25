# Poker Demo API Documentation

This document describes the HTTP API endpoints for the Poker Demo backend server. Use these endpoints to interact with the game server from the command line (e.g., using curl, httpie, or similar tools).

## Endpoints

### 1. Create a New Game
- **POST** `/game/new`
- **Description:** Create a new poker table.
- **Request Body:**
```json
{
  "player_name": "Dealer",        // Name of the creator
  "num_players": 2-9,              // Number of seats (default: 6)
  "starting_chips": 1000,          // Chips per player (default: 1000)
  "small_blind": 5,                // Small blind amount (default: 5)
  "big_blind": 10                  // Big blind amount (default: 10)
}
```
- **Response:**
```json
{
  "game_id": "...",
  "player_id": 0,
  ... // Full game state
}
```

---

### 2. Join a Game
- **POST** `/game/<game_id>/join`
- **Description:** Join an existing game at an available seat.
- **Request Body:**
```json
{
  "player_name": "Player"
}
```
- **Response:**
```json
{
  "player_id": <seat_index>,
  ... // Full game state
}
```

---

### 3. Get Game State
- **GET** `/game/<game_id>`
- **Description:** Retrieve the current state of a game.
- **Response:**
```json
{
  ... // Full game state
}
```

---

### 4. Player Action
- **POST** `/game/<game_id>/action`
- **Description:** Submit an action for a player (fold, check, call, raise).
- **Request Body:**
```json
{
  "player_id": <seat_index>,
  "action": "fold" | "check" | "call" | "raise",
  "amount": <raise_amount> // Only for "raise"
}
```
- **Response:**
```json
{
  ... // Updated game state or error
}
```

---

### 5. Deal Next Hand (Manual)
- **POST** `/game/<game_id>/deal`
- **Description:** Manually start the next hand (only allowed after showdown).
- **Response:**
```json
{
  ... // Updated game state
}
```

---

## Example Usage (curl)

### Create a New Game
```
curl -X POST http://localhost:5001/game/new \
  -H "Content-Type: application/json" \
  -d '{"player_name": "Dealer", "num_players": 3}'
```

### Join a Game
```
curl -X POST http://localhost:5001/game/<game_id>/join \
  -H "Content-Type: application/json" \
  -d '{"player_name": "Alice"}'
```

### Get Game State
```
curl http://localhost:5001/game/<game_id>
```

### Player Action
```
curl -X POST http://localhost:5001/game/<game_id>/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "call"}'
```

### Deal Next Hand
```
curl -X POST http://localhost:5001/game/<game_id>/deal
```

---

## Notes
- All endpoints return JSON.
- Replace `<game_id>` with your actual game ID.
- Replace `<seat_index>` with your assigned player ID.
- Actions must be performed in turn order.

---

## WebSocket Usage

The Poker Demo server supports real-time updates via WebSocket (Socket.IO). 

### WebSocket URL
```
ws://localhost:5001
```

### Key Events

- `join_game_room` (emit): Join a game room for updates.
  - Payload: `{ game_id: string, player_id: number, player_name: string }`

- `game_state_update` (receive): Broadcasts the latest game state after any change.
  - Payload: `{ game_state: {...} }`

- `game_action` (receive): Notifies when a player acts.
  - Payload: `{ game_id, player_id, action, game_state }`

- `player_joined` (receive): Notifies when a new player joins.
  - Payload: `{ game_id, player_name, game_state }`

### Example Python Client (socketio)
```python
import socketio

sio = socketio.Client()

@sio.event
def connect():
    print("Connected to server")
    sio.emit('join_game_room', {'game_id': '<game_id>', 'player_id': <player_id>, 'player_name': 'LLM Bot'})

@sio.on('game_state_update')
def on_game_state(data):
    print("Game state updated:", data)
    # If it's your turn, decide and act

@sio.on('game_action')
def on_game_action(data):
    print("Player action:", data)

sio.connect('http://localhost:5001')
```

### Usage Notes
- Use WebSocket events to get instant updates and act when it's your turn.
- You can POST actions via HTTP or extend the server to accept actions via WebSocket.

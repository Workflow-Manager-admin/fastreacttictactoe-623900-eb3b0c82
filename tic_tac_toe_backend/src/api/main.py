from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid

app = FastAPI(
    title="Tic Tac Toe Backend API",
    description="Backend API for a persistent Tic Tac Toe game, supporting human vs human and human vs AI play.",
    version="0.1.0",
    openapi_tags=[
        {"name": "Game", "description": "Game creation, moves, and state."},
        {"name": "History", "description": "Game history and retrieval."}
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================== Models ==============================
PLAYER = Literal["X", "O"]
GameStatus = Literal["in_progress", "draw", "win"]

class MoveModel(BaseModel):
    """Model representing a move action."""
    player: PLAYER = Field(..., description="The player making the move (X or O).")
    row: int = Field(..., ge=0, le=2, description="Row index of the move (0-2).")
    col: int = Field(..., ge=0, le=2, description="Column index of the move (0-2).")

class GameCreateRequest(BaseModel):
    """Request body for creating a new game."""
    versus_ai: Optional[bool] = Field(default=False, description="True if playing against AI.")

class GameStateResponse(BaseModel):
    """State of a Tic Tac Toe game."""
    game_id: str = Field(..., description="Game identifier.")
    board: List[List[Optional[PLAYER]]] = Field(..., description="3x3 board as a list of lists.")
    next_player: PLAYER = Field(..., description="Player whose turn is next.")
    status: GameStatus = Field(..., description="Game status: in_progress, win, or draw.")
    winner: Optional[PLAYER] = Field(default=None, description="Winner (if game over).")
    versus_ai: bool = Field(..., description="Was the game played against AI.")
    message: Optional[str] = Field(default=None, description="UI/status message for the game.")

class GameHistoryEntry(BaseModel):
    """A single game history record."""
    game_id: str
    start_time: str
    end_time: Optional[str]
    versus_ai: bool
    winner: Optional[PLAYER]

class GameHistoryResponse(BaseModel):
    """Response containing a list of previous games."""
    games: List[GameHistoryEntry]

# ============================ In-memory Game Store ============================
# In a real app, these would be managed by a persistent database service.
GAMES = {}

# ============================== Core Game Logic ==============================
# PUBLIC_INTERFACE
def new_game(versus_ai: bool = False) -> GameStateResponse:
    """Start a new game (vs AI or human)."""
    game_id = str(uuid.uuid4())
    game_data = {
        "game_id": game_id,
        "board": [[None for _ in range(3)] for _ in range(3)],
        "next_player": "X",
        "status": "in_progress",
        "winner": None,
        "moves": [],
        "versus_ai": versus_ai,
        "start_time": "", # Would be datetime in prod
        "end_time": None,
    }
    GAMES[game_id] = game_data
    return GameStateResponse(
        game_id=game_id,
        board=game_data["board"],
        next_player=game_data["next_player"],
        status=game_data["status"],
        winner=game_data["winner"],
        versus_ai=game_data["versus_ai"],
        message="New game started. X to move."
    )

# PUBLIC_INTERFACE
def make_move(game_id: str, move: MoveModel) -> GameStateResponse:
    """Apply a move and update game state."""
    if game_id not in GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    game = GAMES[game_id]
    if game["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="Game is already over.")
    # Validate move
    if (move.row < 0 or move.row > 2 or move.col < 0 or move.col > 2 or
            game["board"][move.row][move.col] is not None):
        raise HTTPException(status_code=400, detail="Invalid move position.")
    if move.player != game["next_player"]:
        raise HTTPException(status_code=400, detail="It's not that player's turn.")
    # Place move
    game["board"][move.row][move.col] = move.player
    game["moves"].append({"player": move.player, "row": move.row, "col": move.col})
    winner = check_winner(game["board"])
    # Update game state
    if winner:
        game["status"] = "win"
        game["winner"] = move.player
        game["end_time"] = "" # Datetime in real impl
        msg = f"{move.player} wins!"
    elif is_draw(game["board"]):
        game["status"] = "draw"
        game["winner"] = None
        game["end_time"] = ""
        msg = "The game is a draw."
    else:
        game["next_player"] = "O" if move.player == "X" else "X"
        msg = f"{game['next_player']}'s turn."
        # AI move (if enabled and it's AI's turn)
        if game["versus_ai"] and game["next_player"] == "O":
            ai_move_coords = get_ai_move(game["board"])
            if ai_move_coords:
                game["board"][ai_move_coords[0]][ai_move_coords[1]] = "O"
                game["moves"].append({"player": "O", "row": ai_move_coords[0], "col": ai_move_coords[1]})
                winner = check_winner(game["board"])
                if winner:
                    game["status"] = "win"
                    game["winner"] = "O"
                    game["end_time"] = ""
                    msg = "O (AI) wins!"
                elif is_draw(game["board"]):
                    game["status"] = "draw"
                    msg = "The game is a draw."
                else:
                    game["next_player"] = "X"
                    msg = "X's turn."
    return GameStateResponse(
        game_id=game["game_id"],
        board=game["board"],
        next_player=game["next_player"],
        status=game["status"],
        winner=game["winner"],
        versus_ai=game["versus_ai"],
        message=msg
    )

def check_winner(board: List[List[Optional[str]]]) -> Optional[str]:
    """Check for a winner."""
    lines = (
        # rows
        *board,
        # columns
        [ [board[r][i] for r in range(3)] for i in range(3) ],
        # diagonals
        [ [board[i][i] for i in range(3)] ],
        [ [board[i][2-i] for i in range(3)] ],
    )
    for line in lines:
        for candidate in line:
            if candidate and all(cell == candidate for cell in line):
                return candidate
    return None

def is_draw(board: List[List[Optional[str]]]) -> bool:
    """Check if the board is full and no winner."""
    return all(all(cell is not None for cell in row) for row in board) and not check_winner(board)

def get_ai_move(board: List[List[Optional[str]]]) -> Optional[List[int]]:
    """Simple AI that picks the first available spot."""
    for i in range(3):
        for j in range(3):
            if board[i][j] is None:
                return [i, j]
    return None

# ============================== API ENDPOINTS ==============================

@app.get("/", tags=["Game"], summary="Health Check", description="API health check endpoint.")
def health_check():
    """Returns API health status."""
    return {"message": "Healthy"}

# PUBLIC_INTERFACE
@app.post("/games", response_model=GameStateResponse, tags=["Game"], summary="Start new game")
def create_game(body: GameCreateRequest = Body(...)):
    """
    Start a new tic tac toe game.

    Parameters:
    - versus_ai: bool (optional): play against AI if true.

    Returns the initial game state.
    """
    return new_game(versus_ai=body.versus_ai)

# PUBLIC_INTERFACE
@app.post("/games/{game_id}/move", response_model=GameStateResponse, tags=["Game"], summary="Make a move")
def make_move_endpoint(game_id: str, move: MoveModel):
    """
    Make a move in a game.

    Parameters:
      - game_id: The unique game identifier.
      - move: row, col, and player info.

    Returns the updated game state.
    """
    return make_move(game_id, move)

# PUBLIC_INTERFACE
@app.get("/games/{game_id}", response_model=GameStateResponse, tags=["Game"], summary="Get game state")
def game_state(game_id: str):
    """
    Fetch the current state of a given game.
    """
    if game_id not in GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    g = GAMES[game_id]
    return GameStateResponse(
        game_id=game_id,
        board=g["board"],
        next_player=g["next_player"],
        status=g["status"],
        winner=g["winner"],
        versus_ai=g["versus_ai"],
        message=None
    )

# PUBLIC_INTERFACE
@app.get("/history", response_model=GameHistoryResponse, tags=["History"], summary="Get game history")
def game_history():
    """
    Get the list of previous games (from memory; database integration can be added later).
    """
    history = []
    for g in GAMES.values():
        history.append(GameHistoryEntry(
            game_id=g["game_id"],
            start_time=g.get("start_time", ""),
            end_time=g.get("end_time"),
            versus_ai=g.get("versus_ai", False),
            winner=g.get("winner")
        ))
    return GameHistoryResponse(games=history)

# ------------------- Placeholder for Database Integration -------------------
# In the future, replace GAMES with persistent DB access.
# (e.g., via dependency-injected CRUD classes, using the 'tic_tac_toe_database' container.)


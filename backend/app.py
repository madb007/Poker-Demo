from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from typing import List, Dict, Optional
from collections import Counter
import random
import uuid
import threading
import os
import json
import urllib.request

# Import generators
from pokerkit_generator import generate_hands_pokerkit
# from pyro_generator import generate_hands_pyro

# Import PokerKit
from pokerkit import Card, Rank, Suit, StandardHighHand, Deck
import itertools


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory storage for game tables and connections
games = {}
game_connections = {}  # Maps game_id to list of connected player names
player_assignments = {}  # Maps (game_id, session_id) to player_id
auto_deal_timers = {}  # Maps game_id to timer for auto-dealing next hand
bot_action_timers = {}  # Maps game_id to timer for bot actions

# Player types
PLAYER_TYPE_HUMAN = "human"
PLAYER_TYPE_DEMO = "demo"
PLAYER_TYPE_LLM = "llm"


# Mapping from frontend format to PokerKit
RANK_MAP = {
    "2": Rank.DEUCE, "3": Rank.TREY, "4": Rank.FOUR, "5": Rank.FIVE,
    "6": Rank.SIX, "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE,
    "T": Rank.TEN, "J": Rank.JACK, "Q": Rank.QUEEN, "K": Rank.KING, "A": Rank.ACE
}

SUIT_MAP = {
    "hearts": Suit.HEART, "diamonds": Suit.DIAMOND, 
    "clubs": Suit.CLUB, "spades": Suit.SPADE
}

# Reverse mappings for serialization
RANK_TO_STR = {v: k for k, v in RANK_MAP.items()}
SUIT_TO_STR = {
    Suit.HEART: "hearts", Suit.DIAMOND: "diamonds",
    Suit.CLUB: "clubs", Suit.SPADE: "spades"
}


def card_to_dict(card: Card) -> dict:
    """Convert PokerKit Card to frontend dict format."""
    return {"rank": RANK_TO_STR[card.rank], "suit": SUIT_TO_STR[card.suit]}


def card_from_dict(d: dict) -> Card:
    """Convert frontend dict to PokerKit Card."""
    return Card(RANK_MAP[d["rank"]], SUIT_MAP[d["suit"]])


def create_deck() -> List[Card]:
    """Create a standard 52-card deck using PokerKit Cards."""
    ranks = [Rank.DEUCE, Rank.TREY, Rank.FOUR, Rank.FIVE, Rank.SIX, 
             Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.JACK, 
             Rank.QUEEN, Rank.KING, Rank.ACE]
    suits = [Suit.HEART, Suit.DIAMOND, Suit.CLUB, Suit.SPADE]
    return [Card(rank, suit) for rank in ranks for suit in suits]


def shuffle_deck(deck: List[Card]) -> List[Card]:
    """Shuffle a deck."""
    shuffled = deck.copy()
    random.shuffle(shuffled)
    return shuffled


def start_game(game_state: Dict) -> None:
    """Start a poker game by dealing cards and initializing the first hand."""
    # Promote pending players to active
    for player in game_state["players"]:
        if player.get("pending_active"):
            player["is_active"] = True
            player["pending_active"] = False

    # Get indices of active players (maintains order, exclude pending)
    active_indices = [i for i, p in enumerate(game_state["players"]) if p["is_active"] and not p.get("pending_active", False)]
    
    if len(active_indices) < 2:
        return  # Need at least 2 players
    
    # Reset folded status and bets for all active players
    for i in active_indices:
        game_state["players"][i]["folded"] = False
        game_state["players"][i]["current_bet"] = 0
        game_state["players"][i]["acted_this_round"] = False
    
    # Reset community cards for new hand
    game_state["community_cards"] = []
    # Change game stage
    game_state["game_stage"] = "pre_flop"
    
    # Create and shuffle deck
    deck = shuffle_deck(create_deck())
    
    # Deal hole cards to each active player
    card_index = 0
    for i in active_indices:
        game_state["players"][i]["hole_cards"] = [
            card_to_dict(deck[card_index]),
            card_to_dict(deck[card_index + 1])
        ]
        card_index += 2
    
    # Reset blind positions for all players first
    for player in game_state["players"]:
        player["is_dealer"] = False
        player["is_small_blind"] = False
        player["is_big_blind"] = False
    
    # Initialize pot
    game_state["pot"] = 0
    
    # Set up blinds
    if len(active_indices) >= 2:
        if len(active_indices) == 2:
            # Heads-up: first active player is dealer/small blind and acts first pre-flop
            dealer_idx = active_indices[0]
            big_blind_idx = active_indices[1]
            game_state["players"][dealer_idx]["is_dealer"] = True
            game_state["players"][dealer_idx]["is_small_blind"] = True
            game_state["players"][big_blind_idx]["is_big_blind"] = True
            # Post small blind
            small_blind_amount = game_state["small_blind"]
            game_state["players"][dealer_idx]["chips"] -= small_blind_amount
            game_state["players"][dealer_idx]["current_bet"] = small_blind_amount
            game_state["pot"] += small_blind_amount
            # Post big blind
            big_blind_amount = game_state["big_blind"]
            game_state["players"][big_blind_idx]["chips"] -= big_blind_amount
            game_state["players"][big_blind_idx]["current_bet"] = big_blind_amount
            game_state["pot"] += big_blind_amount
            # Dealer acts first in pre-flop
            game_state["current_player_index"] = dealer_idx
        else:
            # Multi-player: dealer, then small blind, then big blind
            dealer_idx = active_indices[0]
            game_state["players"][dealer_idx]["is_dealer"] = True
            # Small blind is next active player
            small_blind_idx = active_indices[1]
            game_state["players"][small_blind_idx]["is_small_blind"] = True
            # Post small blind
            small_blind_amount = game_state["small_blind"]
            game_state["players"][small_blind_idx]["chips"] -= small_blind_amount
            game_state["players"][small_blind_idx]["current_bet"] = small_blind_amount
            game_state["pot"] += small_blind_amount
            # Big blind is next active player
            big_blind_idx = active_indices[2] if len(active_indices) > 2 else active_indices[0]
            game_state["players"][big_blind_idx]["is_big_blind"] = True
            # Post big blind
            big_blind_amount = game_state["big_blind"]
            game_state["players"][big_blind_idx]["chips"] -= big_blind_amount
            game_state["players"][big_blind_idx]["current_bet"] = big_blind_amount
            game_state["pot"] += big_blind_amount
            # Current player to act is after big blind, but must be a valid active (non-pending) player
            if len(active_indices) > 3:
                game_state["current_player_index"] = active_indices[3]
            else:
                game_state["current_player_index"] = active_indices[0]
    # Ensure current_player_index is always a valid active (non-pending) player
    if game_state["current_player_index"] not in active_indices:
        game_state["current_player_index"] = active_indices[0]
    game_state["current_bet"] = game_state["big_blind"]


def resolve_showdown(game_state: Dict) -> None:
    """Determine winner at showdown and award pot."""
    active_not_folded = [p for p in game_state["players"] if p["is_active"] and not p["folded"]]
    
    if len(active_not_folded) == 0:
        return  # Should not happen
    
    if len(active_not_folded) == 1:
        # One player left (others folded)
        winner = active_not_folded[0]
        winner["chips"] += game_state["pot"]
        game_state["pot"] = 0
        return
    
    # Multiple players still in - evaluate best hands
    if len(game_state["community_cards"]) < 5:
        # Board not complete yet, just award to first non-folded player
        # (shouldn't normally happen)
        winner = active_not_folded[0]
        winner["chips"] += game_state["pot"]
        game_state["pot"] = 0
        return
    
    # Evaluate hands using PokerKit
    board = [card_from_dict(c) for c in game_state["community_cards"]]
    best_hand_value = None
    winner = None
    
    for player in active_not_folded:
        if not player["hole_cards"] or len(player["hole_cards"]) < 2:
            continue
        
        hole_cards = [card_from_dict(c) for c in player["hole_cards"]]
        hand = StandardHighHand.from_game(hole_cards, board)
        
        if best_hand_value is None or hand > best_hand_value:
            best_hand_value = hand
            winner = player
    
    if winner:
        winner["chips"] += game_state["pot"]
        game_state["pot"] = 0


def is_betting_round_complete(game_state: Dict) -> bool:
    """Check if the current betting round is complete."""
    active_not_folded = [p for p in game_state["players"] if p["is_active"] and not p["folded"]]
    
    if len(active_not_folded) <= 1:
        return True  # Everyone folded
    
    # Check if all players have acted and matched the current bet
    for player in active_not_folded:
        # Player hasn't acted yet this round
        if not player.get("acted_this_round", False):
            return False
        # Player hasn't matched the current bet
        if player["current_bet"] < game_state["current_bet"]:
            return False
    
    return True
    """Check if the current betting round is complete."""
    active_not_folded = [p for p in game_state["players"] if p["is_active"] and not p["folded"]]
    
    if len(active_not_folded) <= 1:
        return True  # Everyone folded
    
    # Check if all players have either folded or matched the current bet
    for player in active_not_folded:
        if player["current_bet"] < game_state["current_bet"]:
            return False  # Someone hasn't matched the current bet
    
    return True


def auto_deal_next_hand(game_id: str) -> None:
    """Automatically deal the next hand after a delay."""
    if game_id not in games:
        return
    
    game_state = games[game_id]
    start_game(game_state)
    
    # Broadcast the new game state
    socketio.emit(
        'game_state_update',
        {'game_state': game_state},
        room=game_id
    )

    maybe_trigger_bot_turn(game_id)
    
    # Remove the timer from tracking
    if game_id in auto_deal_timers:
        del auto_deal_timers[game_id]


def progress_betting_round(game_state: Dict) -> None:
    """Move to the next betting round or showdown."""
    # Check if only one player left
    active_not_folded = [p for p in game_state["players"] if p["is_active"] and not p["folded"]]
    if len(active_not_folded) <= 1:
        game_state["game_stage"] = "showdown"
        return
    
    # Reset bets for next round and update stage
    for player in game_state["players"]:
        if player["is_active"] and not player["folded"]:
            player["current_bet"] = 0
            player["acted_this_round"] = False
    
    game_state["current_bet"] = 0
    
    # Progress to next stage
    if game_state["game_stage"] == "pre_flop":
        # Deal flop (3 cards)
        deck = shuffle_deck(create_deck())
        # Convert all used cards to Card objects for comparison
        used_card_objs = [card_from_dict(c) for c in game_state["community_cards"]]
        used_card_objs += [card_from_dict(c) for p in game_state["players"] for c in p["hole_cards"] if c]
        available = [c for c in deck if c not in used_card_objs]
        game_state["community_cards"] = [card_to_dict(c) for c in available[:3]]
        game_state["game_stage"] = "flop"
        
    elif game_state["game_stage"] == "flop":
        # Deal turn (1 card)
        deck = shuffle_deck(create_deck())
        used_card_objs = [card_from_dict(c) for c in game_state["community_cards"]]
        used_card_objs += [card_from_dict(c) for p in game_state["players"] for c in p["hole_cards"] if c]
        available = [c for c in deck if c not in used_card_objs]
        new_card = available[0]
        game_state["community_cards"].append(card_to_dict(new_card))
        game_state["game_stage"] = "turn"
        
    elif game_state["game_stage"] == "turn":
        # Deal river (1 card)
        deck = shuffle_deck(create_deck())
        used_card_objs = [card_from_dict(c) for c in game_state["community_cards"]]
        used_card_objs += [card_from_dict(c) for p in game_state["players"] for c in p["hole_cards"] if c]
        available = [c for c in deck if c not in used_card_objs]
        new_card = available[0]
        game_state["community_cards"].append(card_to_dict(new_card))
        game_state["game_stage"] = "river"
        
    elif game_state["game_stage"] == "river":
        game_state["game_stage"] = "showdown"
    
    # Find first player to act in new round
    active_not_folded = [p for p in game_state["players"] if p["is_active"] and not p["folded"]]
    if active_not_folded and len(active_not_folded) > 1:
        # Small blind acts first post-flop, otherwise find first non-dealer
        small_blind_player = next((i for i, p in enumerate(game_state["players"]) if p["is_active"] and p.get("is_small_blind")), None)
        if small_blind_player is not None:
            game_state["current_player_index"] = small_blind_player
        else:
            # Fallback: find first non-dealer player
            for i, player in enumerate(game_state["players"]):
                if player["is_active"] and not player["folded"] and not player["is_dealer"]:
                    game_state["current_player_index"] = i
                    break


def is_bot_player(player: Dict) -> bool:
    return player.get("player_type") in {PLAYER_TYPE_DEMO, PLAYER_TYPE_LLM}


def compute_valid_actions(game_state: Dict, player: Dict) -> Dict:
    valid = ["fold"]
    if game_state["current_bet"] == player["current_bet"]:
        valid.append("check")
    else:
        valid.append("call")

    min_raise = max(
        game_state["current_bet"] + game_state["big_blind"],
        game_state["current_bet"] * 2
    )
    max_raise = player["current_bet"] + player["chips"]

    if max_raise >= min_raise and player["chips"] > 0:
        valid.append("raise")

    return {
        "valid_actions": valid,
        "min_raise": min_raise,
        "max_raise": max_raise
    }


def safe_default_action(game_state: Dict, player: Dict) -> Dict:
    action_info = compute_valid_actions(game_state, player)
    if "check" in action_info["valid_actions"]:
        return {"action": "check", "amount": 0}
    if "call" in action_info["valid_actions"]:
        return {"action": "call", "amount": 0}
    return {"action": "fold", "amount": 0}


def demo_bot_action(game_state: Dict, player: Dict) -> Dict:
    # Placeholder policy - replace with your probabilistic demo logic.
    return safe_default_action(game_state, player)


def call_ollama(messages: list) -> Optional[str]:
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            body = json.loads(res.read().decode("utf-8"))
            return body.get("message", {}).get("content", "")
    except Exception:
        return None


def parse_llm_action(text: str) -> Optional[Dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to extract JSON object from free-form text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


def llm_bot_action(game_state: Dict, player: Dict) -> Dict:
    action_info = compute_valid_actions(game_state, player)
    prompt_payload = {
        "player_id": player["id"],
        "player_name": player["name"],
        "player_chips": player["chips"],
        "player_current_bet": player["current_bet"],
        "player_hole_cards": player.get("hole_cards", []),
        "community_cards": game_state["community_cards"],
        "pot": game_state["pot"],
        "current_bet": game_state["current_bet"],
        "min_raise": action_info["min_raise"],
        "max_raise": action_info["max_raise"],
        "valid_actions": action_info["valid_actions"],
        "game_stage": game_state["game_stage"],
        "opponents": [
            {
                "id": p["id"],
                "name": p["name"],
                "chips": p["chips"],
                "folded": p["folded"],
                "current_bet": p["current_bet"]
            }
            for p in game_state["players"] if p["id"] != player["id"]
        ],
        "blinds": {
            "small_blind": game_state["small_blind"],
            "big_blind": game_state["big_blind"]
        }
    }

    system = "You are a poker bot. Return ONLY valid JSON: {\"action\":\"fold|check|call|raise\",\"amount\":number|null,\"reason\":string}."
    user = f"State: {json.dumps(prompt_payload)}"

    content = call_ollama([
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ])

    parsed = parse_llm_action(content or "")
    if not parsed:
        return safe_default_action(game_state, player)

    action = parsed.get("action")
    amount = parsed.get("amount", 0)

    if action not in action_info["valid_actions"]:
        return safe_default_action(game_state, player)

    if action == "raise":
        try:
            amount_val = int(amount)
        except Exception:
            return safe_default_action(game_state, player)
        if amount_val < action_info["min_raise"] or amount_val > action_info["max_raise"]:
            return safe_default_action(game_state, player)
        return {"action": "raise", "amount": amount_val}

    return {"action": action, "amount": 0}


def maybe_trigger_bot_turn(game_id: str) -> None:
    if game_id not in games:
        return
    game_state = games[game_id]
    if game_state["game_stage"] in {"waiting", "showdown"}:
        return
    current_idx = game_state.get("current_player_index", -1)
    if current_idx < 0 or current_idx >= len(game_state["players"]):
        return
    player = game_state["players"][current_idx]
    if not (player["is_active"] and not player["folded"] and is_bot_player(player)):
        return

    existing = bot_action_timers.get(game_id)
    if existing:
        existing.cancel()

    timer = threading.Timer(0.6, bot_take_action, args=[game_id])
    timer.daemon = True
    timer.start()
    bot_action_timers[game_id] = timer


def bot_take_action(game_id: str) -> None:
    if game_id not in games:
        return
    game_state = games[game_id]
    current_idx = game_state.get("current_player_index", -1)
    if current_idx < 0 or current_idx >= len(game_state["players"]):
        return
    player = game_state["players"][current_idx]
    if not (player["is_active"] and not player["folded"] and is_bot_player(player)):
        return

    if player.get("player_type") == PLAYER_TYPE_DEMO:
        action_payload = demo_bot_action(game_state, player)
    else:
        action_payload = llm_bot_action(game_state, player)

    process_player_action(
        game_id=game_id,
        player_id=player["id"],
        action=action_payload["action"],
        amount=action_payload.get("amount", 0),
        emit_events=True
    )


def process_player_action(game_id: str, player_id: int, action: str, amount: int, emit_events: bool = True):
    game_state = games[game_id]

    if player_id is None or not isinstance(player_id, int):
        return None, "Player ID not assigned yet. Please wait for player_assigned event"

    if action not in ["fold", "check", "call", "raise"]:
        return None, "Invalid action"

    if player_id >= len(game_state["players"]):
        return None, "Invalid player ID"

    if player_id != game_state["current_player_index"]:
        return None, "Not your turn"

    current_player = game_state["players"][player_id]

    if not current_player["is_active"]:
        return None, "Player not active"

    if action == "fold":
        current_player["folded"] = True
        current_player["acted_this_round"] = True

    elif action == "check":
        if game_state["current_bet"] > current_player["current_bet"]:
            return None, "Cannot check, must call or fold"
        current_player["acted_this_round"] = True

    elif action == "call":
        call_amount = game_state["current_bet"] - current_player["current_bet"]
        if call_amount > current_player["chips"]:
            return None, "Insufficient chips to call"

        current_player["chips"] -= call_amount
        current_player["current_bet"] = game_state["current_bet"]
        game_state["pot"] += call_amount
        current_player["acted_this_round"] = True

    elif action == "raise":
        min_raise = max(game_state["current_bet"] + game_state["big_blind"], game_state["current_bet"] * 2)
        if amount < min_raise:
            return None, f"Raise must be at least {min_raise}"

        bet_diff = amount - current_player["current_bet"]
        if bet_diff > current_player["chips"]:
            return None, "Insufficient chips to raise"

        current_player["chips"] -= bet_diff
        current_player["current_bet"] = amount
        game_state["current_bet"] = amount
        game_state["pot"] += bet_diff
        current_player["acted_this_round"] = True

    active_players = [p for p in game_state["players"] if p["is_active"] and not p["folded"]]

    if len(active_players) <= 1:
        game_state["game_stage"] = "showdown"
    else:
        if is_betting_round_complete(game_state):
            progress_betting_round(game_state)
        else:
            next_index = (game_state["current_player_index"] + 1) % len(game_state["players"])
            found = False
            attempts = 0
            while attempts < len(game_state["players"]):
                player = game_state["players"][next_index]
                if (
                    player["is_active"]
                    and not player["folded"]
                    and not player.get("acted_this_round", False)
                ):
                    game_state["current_player_index"] = next_index
                    found = True
                    break
                next_index = (next_index + 1) % len(game_state["players"])
                attempts += 1

            if not found:
                progress_betting_round(game_state)

    games[game_id] = game_state

    if emit_events:
        socketio.emit(
            'game_action',
            {
                'game_id': game_id,
                'player_id': player_id,
                'action': action,
                'game_state': game_state
            },
            room=game_id
        )

    if game_state["game_stage"] == "showdown":
        resolve_showdown(game_state)
        if game_id in auto_deal_timers:
            auto_deal_timers[game_id].cancel()

        timer = threading.Timer(10.0, auto_deal_next_hand, args=[game_id])
        timer.daemon = True
        timer.start()
        auto_deal_timers[game_id] = timer
    else:
        maybe_trigger_bot_turn(game_id)

    return game_state, None


# =============================================================================
# Monte Carlo Simulation  
# =============================================================================


def normalize_hand_name(hand_name: str, cards) -> str:
    #Special Case 
    if hand_name == "Straight flush":
        # Cards are already sorted high to low in StandardHighHand
        card_list = list(cards)
        if card_list[0].rank == Rank.ACE and card_list[1].rank == Rank.KING:
            return "Royal Flush"
        return "Straight Flush"
    
    # Map PokerKit names to UI names
    name_map = {
        "Four of a kind": "Four of a Kind",
        "Full house": "Full House",
        "Flush": "Flush",
        "Straight": "Straight",
        "Three of a kind": "Three of a Kind",
        "Two pair": "Two Pair",
        "One pair": "One Pair",
        "High card": "High Card"
    }
    
    return name_map.get(hand_name, hand_name)


def run_simulation(
    player_hand: List[Card],
    community_cards: List[Card],
    opponent_count: int,
    num_simulations: int = 10000,
) -> Dict:
    wins = 0
    ties = 0
    losses = 0
    hand_counts = Counter()
    
    # Get available cards (deck minus known cards)
    deck = list(Deck.STANDARD)
    known_cards = set(player_hand + community_cards)
    available_cards = [c for c in deck if c not in known_cards]
    
    for _ in range(num_simulations):
        # Shuffle for this simulation
        random.shuffle(available_cards)
        idx = 0
        
        # Complete the board
        sim_board = community_cards.copy()
        cards_needed = 5 - len(sim_board)
        sim_board.extend(available_cards[idx:idx + cards_needed])
        idx += cards_needed
        
        # Deal opponent hands
        opponent_hands = []
        for _ in range(opponent_count):
            opp_hand = available_cards[idx:idx + 2]
            opponent_hands.append(opp_hand)
            idx += 2
        
        # Evaluate player hand using PokerKit
        player_best = StandardHighHand.from_game(player_hand, sim_board)
        
        # Track hand distribution with normalized names
        raw_hand_name = str(player_best).split('(')[0].strip()
        hand_name = normalize_hand_name(raw_hand_name, player_best.cards)
        hand_counts[hand_name] += 1
        
        # Evaluate opponent hands and compare
        player_wins = True
        is_tie = False
        
        for opp_hand in opponent_hands:
            opp_best = StandardHighHand.from_game(opp_hand, sim_board)
            
            if player_best < opp_best:
                # Player loses
                player_wins = False
                break
            elif player_best == opp_best:
                # Tie
                is_tie = True
        
        # Record result
        if player_wins and not is_tie:
            wins += 1
        elif is_tie:
            ties += 1
        else:
            losses += 1
    
    # Normalize hand distribution
    hand_distribution = {k: v / num_simulations for k, v in hand_counts.items()}
    
    return {
        "win_probability": wins / num_simulations,
        "tie_probability": ties / num_simulations,
        "loss_probability": losses / num_simulations,
        "hand_distribution": hand_distribution,
        "simulations_run": num_simulations,
    }


# =============================================================================
# Game Endpoints
@app.route("/game/<game_id>/deal", methods=["POST"])
def manual_deal_next_hand(game_id):
    """Manually deal the next hand for a game."""
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    game_state = games[game_id]
    start_game(game_state)
    games[game_id] = game_state

    # Broadcast the new game state to all players in the room
    socketio.emit(
        'game_state_update',
        {'game_state': game_state},
        room=game_id
    )

    return jsonify(game_state)
# =============================================================================

@app.route("/game/new", methods=["POST"])
def create_new_game():
    """Create a new poker table."""
    data = request.json or {}
    
    player_name = data.get("player_name", "Dealer")
    num_players = min(max(data.get("num_players", 6), 2), 9)  # 2-9 players
    starting_chips = data.get("starting_chips", 1000)
    small_blind = data.get("small_blind", 5)
    big_blind = data.get("big_blind", 10)
    
    game_id = str(uuid.uuid4())
    
    players = []
    for i in range(num_players):
        if i == 0:
            player_type = PLAYER_TYPE_HUMAN
            name = player_name
        elif i == 1:
            player_type = PLAYER_TYPE_DEMO
            name = "Demo Bot"
        else:
            player_type = PLAYER_TYPE_LLM
            name = f"LLM Bot {i - 1}"

        players.append({
            "id": i,
            "name": name,
            "player_type": player_type,
            "chips": starting_chips,
            "hole_cards": [],
            "is_dealer": False,
            "is_small_blind": False,
            "is_big_blind": False,
            "is_active": True,
            "pending_active": False,
            "current_bet": 0,
            "folded": False
        })

    # Initialize game state
    game_state = {
        "game_id": game_id,
        "community_cards": [],
        "pot": 0,
        "current_bet": 0,
        "players": players,
        "current_player_index": -1,
        "game_stage": "waiting",
        "small_blind": small_blind,
        "big_blind": big_blind,
        "max_players": num_players,
        "starting_chips": starting_chips
    }
    
    if len(players) >= 2:
        start_game(game_state)

    games[game_id] = game_state
    maybe_trigger_bot_turn(game_id)
    
    # Return game state with player_id so frontend knows which player they are (creator is always 0)
    response = dict(game_state)
    response['player_id'] = 0
    return jsonify(response)


@app.route("/game/<game_id>", methods=["GET"])
def get_game(game_id):
    """Get current game state."""
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404
    
    return jsonify(games[game_id])


@app.route("/game/<game_id>/join", methods=["POST"])
def join_game(game_id):
    """Join an existing game."""
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404

    data = request.json or {}
    player_name = data.get("player_name", "Player")

    game_state = games[game_id]

    # Find first available inactive seat
    available_seat = None
    available_seat_index = None
    for idx, player in enumerate(game_state["players"]):
        if not player["is_active"] and not player.get("pending_active", False):
            available_seat = player
            available_seat_index = idx
            break

    if available_seat is None:
        return jsonify({"error": "No available seats"}), 400

    # If hand is in progress, allow join but mark as pending
    if game_state["game_stage"] != "waiting":
        available_seat["is_active"] = False
        available_seat["pending_active"] = True
        available_seat["name"] = player_name
    else:
        available_seat["is_active"] = True
        available_seat["pending_active"] = False
        available_seat["name"] = player_name

    # Only start the game when all seats are filled and game hasn't started
    active_count = sum(1 for p in game_state["players"] if p["is_active"])
    if active_count == game_state["max_players"] and game_state["game_stage"] == "waiting":
        start_game(game_state)
        # Broadcast updated game state after starting
        socketio.emit(
            'game_state_update',
            {'game_state': game_state},
            room=game_id
        )

    games[game_id] = game_state

    # Broadcast to all connected players in this game (will be received after client joins room)
    socketio.emit(
        'player_joined',
        {
            'game_id': game_id,
            'player_name': player_name,
            'game_state': game_state
        },
        room=game_id
    )

    # Return game state with player_id so frontend knows which player they are
    response = dict(game_state)
    response['player_id'] = available_seat_index
    return jsonify(response)



@app.route("/game/<game_id>/action", methods=["POST"])
def player_action(game_id):
    """Handle player action (fold, check, call, raise) with No-Limit Hold'em rules."""
    if game_id not in games:
        return jsonify({"error": "Game not found"}), 404
    
    data = request.json or {}
    player_id = data.get("player_id")
    action = data.get("action", "")
    amount = data.get("amount", 0)

    game_state, error = process_player_action(
        game_id=game_id,
        player_id=player_id,
        action=action,
        amount=amount,
        emit_events=True
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify(game_state)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "engine": "Monte Carlo Poker Simulator"})


@app.route("/llm/health", methods=["GET"])
def llm_health():
    """Check if Ollama is reachable."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2):
            return jsonify({"status": "ok"}), 200
    except Exception:
        return jsonify({"status": "offline"}), 503


@app.route("/deal", methods=["POST"])
def deal():
    """Deal a new hand."""
    data = request.json or {}
    opponent_count = data.get("opponent_count", 1)

    deck = shuffle_deck(create_deck())
    player_hand = deck[:2]

    return jsonify(
        {
            "player_hand": [card_to_dict(c) for c in player_hand],
            "opponent_count": opponent_count,
        }
    )


@app.route("/community", methods=["POST"])
def deal_community():
    """Deal community cards."""
    data = request.json or {}
    current_cards = [card_from_dict(c) for c in data.get("current_cards", [])]
    player_hand = [card_from_dict(c) for c in data.get("player_hand", [])]
    count = data.get("count", 3)

    known_cards = set(current_cards + player_hand)
    deck = [c for c in create_deck() if c not in known_cards]
    random.shuffle(deck)

    new_cards = deck[:count]
    all_community = current_cards + new_cards

    return jsonify({"community_cards": [card_to_dict(c) for c in all_community]})


@app.route("/simulate", methods=["POST"])
def simulate():
    """Run Monte Carlo simulation."""
    data = request.json or {}

    player_hand = [card_from_dict(c) for c in data.get("player_hand", [])]
    community_cards = [card_from_dict(c) for c in data.get("community_cards", [])]
    opponent_count = data.get("opponent_count", 1)
    num_simulations = min(data.get("num_simulations", 10000), 200000)

    if len(player_hand) != 2:
        return jsonify({"error": "Player hand must have exactly 2 cards"}), 400

    results = run_simulation(
        player_hand=player_hand,
        community_cards=community_cards,
        opponent_count=opponent_count,
        num_simulations=num_simulations,
    )

    return jsonify(results)


@app.route("/benchmark", methods=["POST"])
def benchmark():
    """Benchmark hand generation between PokerKit and Pyro."""
    data = request.json or {}
    
    method = data.get("method", "pokerkit")  # 'pokerkit' or 'pyro'
    num_hands = data.get("num_hands", 1000)
    num_players = data.get("num_players", 2)
    
    # Cap at reasonable limits
    num_hands = min(num_hands, 100000)
    num_players = min(max(num_players, 2), 9)
    
    try:
        if method == "pokerkit":
            results = generate_hands_pokerkit(num_hands, num_players)
        elif method == "pyro":
            results = generate_hands_pyro(num_hands, num_players)
        else:
            return jsonify({"error": "Invalid method. Use 'pokerkit' or 'pyro'"}), 400
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/evaluate", methods=["POST"])
def evaluate():
    """Evaluate a specific hand using PokerKit."""
    data = request.json or {}
    cards = [card_from_dict(c) for c in data.get("cards", [])]

    if len(cards) < 5:
        return jsonify({"error": "Need at least 5 cards"}), 400

    # Use PokerKit to evaluate
    if len(cards) == 5:
        hand = StandardHighHand(cards)
    else:
        # For 6 or 7 cards, find best hand (hole + board scenario)
        hole = cards[:2]
        board = cards[2:]
        hand = StandardHighHand.from_game(hole, board)

    hand_str = str(hand)
    hand_name = hand_str.split('(')[0].strip()

    return jsonify(
        {
            "hand_name": hand_name,
            "hand_description": hand_str,
        }
    )


# =============================================================================
# WebSocket Events
# =============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    print(f'Client connected: {request.sid}')


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print(f'Client disconnected: {request.sid}')


@socketio.on('join_game_room')
def handle_join_game_room(data):
    """Join a game room for real-time updates."""
    game_id = data.get('game_id')
    player_name = data.get('player_name')
    player_id = data.get('player_id')  # Get the player_id from the client
    
    if not game_id:
        emit('error', {'message': 'Game ID required'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    # Join the socket room
    join_room(game_id)
    
    # Track connection
    if game_id not in game_connections:
        game_connections[game_id] = []
    if player_name not in game_connections[game_id]:
        game_connections[game_id].append(player_name)
    
    # Validate player_id if provided, otherwise find it by name
    game_state = games[game_id]
    
    # Convert player_id to int if it's a string
    if isinstance(player_id, str):
        try:
            player_id = int(player_id)
        except (ValueError, TypeError):
            player_id = None
    
    # Use provided player_id if it's valid
    if isinstance(player_id, int) and 0 <= player_id < len(game_state["players"]) and game_state["players"][player_id]["is_active"]:
        # player_id is valid and points to an active player, use it
        pass
    else:
        # Fallback: find by name (only if player_id wasn't provided or was invalid)
        player_id = None
        for idx, player in enumerate(game_state["players"]):
            if player["name"] == player_name and player["is_active"]:
                player_id = idx
                break
    
    # Store the player_id assignment for this session
    player_assignments[(game_id, request.sid)] = player_id
    
    # Send player_id back to the client
    emit('player_assigned', {
        'player_id': player_id,
        'player_name': player_name,
        'game_id': game_id
    })
    
    # Notify others in the room
    emit('player_connected', {
        'player_name': player_name,
        'game_id': game_id,
        'connected_players': game_connections.get(game_id, [])
    }, room=game_id)
    
    # Send current game state only if game has started
    if games[game_id]["game_stage"] != "waiting":
        emit('game_state_update', {'game_state': games[game_id]})


@socketio.on('leave_game_room')
def handle_leave_game_room(data):
    """Leave a game room."""
    game_id = data.get('game_id')
    player_name = data.get('player_name')
    
    if game_id and game_id in game_connections:
        if player_name in game_connections[game_id]:
            game_connections[game_id].remove(player_name)
        
        leave_room(game_id)
        
        emit('player_disconnected', {
            'player_name': player_name,
            'game_id': game_id,
            'connected_players': game_connections.get(game_id, [])
        }, room=game_id)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)

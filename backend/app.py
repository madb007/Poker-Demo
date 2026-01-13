from flask import Flask, request, jsonify
from flask_cors import CORS
from typing import List, Dict
from collections import Counter
import random

# Import generators
from pokerkit_generator import generate_hands_pokerkit
from pyro_generator import generate_hands_pyro

# Import PokerKit
from pokerkit import Card, Rank, Suit, StandardHighHand, Deck
import itertools


app = Flask(__name__)
CORS(app)


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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "engine": "Monte Carlo Poker Simulator"})


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

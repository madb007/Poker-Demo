from __future__ import annotations

import json
from typing import Dict, Optional

try:
    import torch
    from pyro_generator import CategoricalSansReplacement
    PYRO_AVAILABLE = True
except Exception:
    torch = None
    CategoricalSansReplacement = None
    PYRO_AVAILABLE = False

from pokerkit import Card, Rank, Suit, StandardHighHand, Deck

from llm_client import LLMClient

PLAYER_TYPE_HUMAN = "human"
PLAYER_TYPE_DEMO = "demo"
PLAYER_TYPE_LLM = "llm"
PLAYER_TYPE_OPEN = "open"


def create_player(
    seat_id: int,
    name: str,
    player_type: str,
    starting_chips: int,
    is_active: bool,
    pending_active: bool = False,
    seat_type: Optional[str] = None,
) -> Dict:
    return {
        "id": seat_id,
        "name": name,
        "player_type": player_type,
        "seat_type": seat_type or player_type,
        "chips": starting_chips,
        "hole_cards": [],
        "is_dealer": False,
        "is_small_blind": False,
        "is_big_blind": False,
        "is_active": is_active,
        "pending_active": pending_active,
        "current_bet": 0,
        "folded": False,
        "acted_this_round": False,
        "last_action": None,
    }


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
        game_state["current_bet"] * 2,
    )
    max_raise = player["current_bet"] + player["chips"]

    if max_raise >= min_raise and player["chips"] > 0:
        valid.append("raise")

    return {
        "valid_actions": valid,
        "min_raise": min_raise,
        "max_raise": max_raise,
    }


def safe_default_action(game_state: Dict, player: Dict) -> Dict:
    action_info = compute_valid_actions(game_state, player)
    if "check" in action_info["valid_actions"]:
        return {"action": "check", "amount": 0}
    if "call" in action_info["valid_actions"]:
        return {"action": "call", "amount": 0}
    return {"action": "fold", "amount": 0}


def demo_bot_action(game_state: Dict, player: Dict) -> Dict:
    action_info = compute_valid_actions(game_state, player)

    equity = estimate_equity(game_state, player, num_simulations=200)
    to_call = max(game_state["current_bet"] - player["current_bet"], 0)

    if to_call > 0 and equity < 0.35 and "fold" in action_info["valid_actions"]:
        return {"action": "fold", "amount": 0}

    if equity >= 0.6 and "raise" in action_info["valid_actions"]:
        kelly = max((equity * 2) - 1, 0)
        bet_size = int(player["chips"] * kelly * 0.5)
        raise_to = game_state["current_bet"] + max(bet_size, game_state["big_blind"])
        raise_to = max(raise_to, action_info["min_raise"])
        raise_to = min(raise_to, action_info["max_raise"])
        if raise_to >= action_info["min_raise"]:
            return {"action": "raise", "amount": raise_to}

    if "call" in action_info["valid_actions"] and to_call > 0:
        return {"action": "call", "amount": 0}

    return {"action": "check", "amount": 0}


def estimate_equity(game_state: Dict, player: Dict, num_simulations: int = 200) -> float:
    active_opponents = [
        p for p in game_state["players"]
        if p["id"] != player["id"] and p["is_active"] and not p["folded"]
    ]
    if not active_opponents:
        return 1.0

    hole_cards = [card_from_dict(c) for c in player.get("hole_cards", [])]
    community_cards = [card_from_dict(c) for c in game_state.get("community_cards", [])]
    if len(hole_cards) != 2:
        return 0.0

    deck = list(Deck.STANDARD)
    known_cards = set(hole_cards + community_cards)
    remaining = [c for c in deck if c not in known_cards]

    board_needed = 5 - len(community_cards)
    opponents_needed = len(active_opponents) * 2
    total_needed = board_needed + opponents_needed
    if total_needed <= 0:
        return 0.0

    wins = 0
    ties = 0
    sims = max(1, num_simulations)

    for _ in range(sims):
        if PYRO_AVAILABLE and CategoricalSansReplacement and torch is not None:
            dist = CategoricalSansReplacement(num_cards_dealt=total_needed, deck_size=len(remaining))
            indices = dist.sample()
            draw = [remaining[i] for i in indices.tolist()]
        else:
            draw = random_sample_without_replacement(remaining, total_needed)

        sim_board = community_cards + draw[:board_needed]
        offset = board_needed

        player_best = StandardHighHand.from_game(hole_cards, sim_board)
        player_wins = True
        is_tie = False

        for opp_idx in range(len(active_opponents)):
            opp_hole = draw[offset + (opp_idx * 2): offset + (opp_idx * 2) + 2]
            opp_best = StandardHighHand.from_game(opp_hole, sim_board)
            if player_best < opp_best:
                player_wins = False
                is_tie = False
                break
            if player_best == opp_best:
                is_tie = True

        if player_wins and not is_tie:
            wins += 1
        elif is_tie:
            ties += 1

    return (wins + (ties * 0.5)) / sims


def random_sample_without_replacement(cards: list[Card], n: int) -> list[Card]:
    if n <= 0:
        return []
    if n >= len(cards):
        return cards[:]
    if torch is not None:
        indices = torch.randperm(len(cards))[:n].tolist()
        return [cards[i] for i in indices]
    return __random_sample(cards, n)


def __random_sample(cards: list[Card], n: int) -> list[Card]:
    import random
    return random.sample(cards, n)


RANK_MAP = {
    "2": Rank.DEUCE, "3": Rank.TREY, "4": Rank.FOUR, "5": Rank.FIVE,
    "6": Rank.SIX, "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE,
    "T": Rank.TEN, "J": Rank.JACK, "Q": Rank.QUEEN, "K": Rank.KING, "A": Rank.ACE
}

SUIT_MAP = {
    "hearts": Suit.HEART, "diamonds": Suit.DIAMOND,
    "clubs": Suit.CLUB, "spades": Suit.SPADE
}


def card_from_dict(d: dict) -> Card:
    return Card(RANK_MAP[d["rank"]], SUIT_MAP[d["suit"]])


def parse_llm_action(text: str) -> Optional[Dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


def llm_bot_action(game_state: Dict, player: Dict, llm_client: LLMClient) -> Dict:
    action_info = compute_valid_actions(game_state, player)
    to_call = max(game_state["current_bet"] - player["current_bet"], 0)
    pot_after_call = game_state["pot"] + to_call
    stack_to_pot = (player["chips"] / pot_after_call) if pot_after_call > 0 else None
    prompt_payload = {
        "player_id": player["id"],
        "player_name": player["name"],
        "player_chips": player["chips"],
        "player_current_bet": player["current_bet"],
        "player_hole_cards": player.get("hole_cards", []),
        "community_cards": game_state["community_cards"],
        "pot": game_state["pot"],
        "current_bet": game_state["current_bet"],
        "to_call": to_call,
        "stack_to_pot_ratio": stack_to_pot,
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
                "current_bet": p["current_bet"],
            }
            for p in game_state["players"]
            if p["id"] != player["id"]
        ],
        "blinds": {
            "small_blind": game_state["small_blind"],
            "big_blind": game_state["big_blind"],
        },
    }

    system = (
        "You are a poker bot. Return ONLY valid JSON: "
        '{"action":"fold|check|call|raise","amount":number|null,"reason":string}. '
        "Do not always check/call; fold weak hands and raise strong ones when appropriate."
    )
    user = f"State: {json.dumps(prompt_payload)}"

    if llm_client.debug:
        print(f"[LLM] request player={player['id']} valid={action_info['valid_actions']}")

    content = llm_client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

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


__all__ = [
    "PLAYER_TYPE_HUMAN",
    "PLAYER_TYPE_DEMO",
    "PLAYER_TYPE_LLM",
    "PLAYER_TYPE_OPEN",
    "create_player",
    "is_bot_player",
    "compute_valid_actions",
    "safe_default_action",
    "demo_bot_action",
    "llm_bot_action",
]

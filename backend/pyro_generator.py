"""Pyro-based poker hand generator for benchmarking."""

import pyro
import torch
from pyro.distributions import TorchDistribution
from pyro.distributions import constraints
import time
from typing import Dict


class CategoricalSansReplacement(TorchDistribution):
    arg_constraints = {}
    support = constraints.integer_interval(0, 51)
    
    def __init__(self, num_cards_dealt: int, deck_size: int = 52, validate_args=None):
        self.num_cards_to_deal = num_cards_dealt
        self.deck_size = deck_size
        batch_shape = torch.Size()
        event_shape = torch.Size([num_cards_dealt])
        super().__init__(batch_shape, event_shape, validate_args=validate_args)

    def sample(self, sample_shape=torch.Size()):
        if not sample_shape:
            # Single sample case
            return torch.randperm(self.deck_size)[:self.num_cards_to_deal]
        
        sample_size = sample_shape.numel()
        samples = torch.stack([
            torch.randperm(self.deck_size)[:self.num_cards_to_deal] 
            for _ in range(sample_size)
        ])
        return samples.reshape(sample_shape + self.event_shape)

    def log_prob(self, value):
        if self._validate_args:
            if (value < 0).any() or (value >= self.deck_size).any():
                return torch.tensor(float("-inf"), device=value.device)
        
            val_flat = value.reshape(-1, self.num_cards_to_deal)
            for row in val_flat:
                if torch.unique(row).numel() != self.num_cards_to_deal:
                    return torch.tensor(float("-inf"), device=value.device)

        n = float(self.deck_size)
        k = float(self.num_cards_to_deal)
        lp = -(torch.lgamma(torch.tensor(n + 1)) - torch.lgamma(torch.tensor(n - k + 1)))
        return lp.expand(value.shape[:-1])


class PokerGenerator:
    def __init__(self, num_players: int):
        self.num_players = num_players
        self.cards_per_player = 2
        self.community_cards = 5
        
        # Calculate total cards needed
        self.total_cards_needed = (num_players * self.cards_per_player) + self.community_cards
        
        # Define the deck lookup - using standard poker notation
        # Suits: H=hearts, D=diamonds, C=clubs, S=spades
        SUITS = ["H", "D", "C", "S"]
        RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        self.deck_lookup = [f"{r}{s}" for r in RANKS for s in SUITS]
        self.deck_size = len(self.deck_lookup)
        
        # Mapping to convert to pokerkit-style format
        self.suit_map = {"H": "heart", "D": "diamond", "C": "club", "S": "spade"}
        self.rank_map = {
            "2": "DEUCE", "3": "TREY", "4": "FOUR", "5": "FIVE",
            "6": "SIX", "7": "SEVEN", "8": "EIGHT", "9": "NINE",
            "10": "TEN", "J": "JACK", "Q": "QUEEN", "K": "KING", "A": "ACE"
        }

    def generate(self):
        """Generate a single hand with player cards and community cards."""
        # Instantiate the custom distribution
        dist = CategoricalSansReplacement(
            num_cards_dealt=self.total_cards_needed, 
            deck_size=self.deck_size
        )
        
        # Sample from the distribution
        indices = pyro.sample("poker_deal", dist)
        
        # Convert tensor indices to card strings
        flat_indices = indices.tolist()
        dealt_cards = [self.deck_lookup[idx] for idx in flat_indices]
        
        # Split into player hands and community cards
        card_idx = 0
        player_hands = []
        
        for _ in range(self.num_players):
            player_hand = []
            for _ in range(self.cards_per_player):
                card_str = dealt_cards[card_idx]
                # Parse card string (e.g., "AH" -> rank="A", suit="H")
                rank = card_str[:-1]
                suit = card_str[-1]
                player_hand.append({
                    'rank': self.rank_map[rank],
                    'suit': self.suit_map[suit]
                })
                card_idx += 1
            player_hands.append(player_hand)
        
        # Remaining cards are community
        community = []
        for _ in range(self.community_cards):
            card_str = dealt_cards[card_idx]
            rank = card_str[:-1]
            suit = card_str[-1]
            community.append({
                'rank': self.rank_map[rank],
                'suit': self.suit_map[suit]
            })
            card_idx += 1
        
        return {
            'player_hands': player_hands,
            'community': community
        }


def generate_hands_pyro(num_hands: int, num_players: int) -> Dict:
    if num_players < 2 or num_players > 9:
        raise ValueError(f"num_players must be between 2 and 9, got {num_players}")
    if num_hands < 0:
        raise ValueError(f"num_hands must be non-negative, got {num_hands}")
    
    start_time = time.perf_counter()
    
    generator = PokerGenerator(num_players)
    generated_hands = []
    valid_hands = 0
    
    for _ in range(num_hands):
        try:
            hand_data = generator.generate()
            generated_hands.append(hand_data)
            valid_hands += 1
        except Exception as e:
            # Skip invalid hands
            continue
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    
    return {
        'method': 'pyro',
        'num_hands': num_hands,
        'num_players': num_players,
        'valid_hands': valid_hands,
        'elapsed_time': elapsed_time,
        'hands_per_second': valid_hands / elapsed_time if elapsed_time > 0 else 0,
        'sample_hands': generated_hands[:5]  # Return first 5 as samples
    }


"""PokerKit-based poker hand generator for benchmarking."""

import random
import time
from typing import List, Dict
from pokerkit import Card, Rank, Suit


def generate_hands_pokerkit(num_hands: int, num_players: int) -> Dict:
    if num_players < 2 or num_players > 9:
        raise ValueError(f"num_players must be between 2 and 9, got {num_players}")
    if num_hands < 0:
        raise ValueError(f"num_hands must be non-negative, got {num_hands}")
    
    start_time = time.perf_counter()
    
    generated_hands = []
    valid_hands = 0
    
    # Standard 52-card deck ranks and suits
    standard_ranks = [Rank.DEUCE, Rank.TREY, Rank.FOUR, Rank.FIVE, Rank.SIX, 
                      Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.JACK, 
                      Rank.QUEEN, Rank.KING, Rank.ACE]
    standard_suits = [Suit.CLUB, Suit.DIAMOND, Suit.HEART, Suit.SPADE]
    
    for _ in range(num_hands):
        try:
            # Create a new deck for each hand
            deck = [Card(rank, suit) for rank in standard_ranks for suit in standard_suits]
            random.shuffle(deck)
            
            # Deal cards to players
            hand_data = {
                'player_hands': [],
                'community': []
            }
            
            card_idx = 0
            
            # Deal 2 cards to each player
            for player_idx in range(num_players):
                player_hand = [deck[card_idx], deck[card_idx + 1]]
                card_idx += 2
                
                hand_data['player_hands'].append([
                    {'rank': str(card.rank.name), 'suit': card.suit.name.lower()}
                    for card in player_hand
                ])
            
            # Deal 5 community cards
            community = [deck[card_idx + i] for i in range(5)]
            hand_data['community'] = [
                {'rank': str(card.rank.name), 'suit': card.suit.name.lower()}
                for card in community
            ]
            
            generated_hands.append(hand_data)
            valid_hands += 1
            
        except Exception as e:
            # Skip invalid hands
            continue
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    
    return {
        'method': 'pokerkit',
        'num_hands': num_hands,
        'num_players': num_players,
        'valid_hands': valid_hands,
        'elapsed_time': elapsed_time,
        'hands_per_second': valid_hands / elapsed_time if elapsed_time > 0 else 0,
        'sample_hands': generated_hands[:5]  # Return first 5 as samples
    }


def validate_hand_pokerkit(player_hands: List, community: List) -> bool:
    all_cards = []
    
    # Collect all cards
    for hand in player_hands:
        for card in hand:
            all_cards.append((card['rank'], card['suit']))
    
    for card in community:
        all_cards.append((card['rank'], card['suit']))
    
    # Check for duplicates
    return len(all_cards) == len(set(all_cards))

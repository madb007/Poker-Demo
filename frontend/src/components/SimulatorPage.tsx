import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// Types
interface Card {
  rank: string;
  suit: string;
}

interface SimulationResult {
  win_probability: number;
  tie_probability: number;
  loss_probability: number;
  hand_distribution: Record<string, number>;
  simulations_run: number;
}

interface GameState {
  player_hand: Card[];
  community_cards: Card[];
  opponent_count: number;
}

// Card display component
const CardDisplay: React.FC<{ card: Card | null; faceDown?: boolean }> = ({ card, faceDown }) => {
  const suitSymbols: Record<string, string> = {
    hearts: '♥',
    diamonds: '♦',
    clubs: '♣',
    spades: '♠'
  };

  const suitColors: Record<string, string> = {
    hearts: '#dc2626',
    diamonds: '#dc2626',
    clubs: '#000000',
    spades: '#000000'
  };

  if (faceDown || !card) {
    return (
      <div className="w-[70px] h-[100px] bg-slate-600 rounded-lg flex items-center justify-center border-2 border-slate-500">
        <div className="text-slate-400 text-2xl">◆</div>
      </div>
    );
  }

  const displayRank = card.rank === 'T' ? '10' : card.rank;

  return (
    <div className="w-[70px] h-[100px] bg-white rounded-xl flex flex-col items-center justify-center border-2 border-slate-300 shadow-xl transition-transform hover:scale-105" style={{ color: suitColors[card.suit] }}>
      <span className="text-2xl font-extrabold leading-none" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{displayRank}</span>
      <span className="text-3xl leading-none mt-0.5">{suitSymbols[card.suit]}</span>
    </div>
  );
};

// Probability bar component
const ProbabilityBar: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
  <div className="space-y-2">
    <div className="flex justify-between items-baseline">
      <span className="text-sm font-medium text-slate-300">{label}</span>
      <span className="font-mono text-lg font-bold text-slate-100" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{(value * 100).toFixed(1)}%</span>
    </div>
    <div className="h-3 bg-slate-800/60 rounded-full overflow-hidden backdrop-blur-sm border border-slate-700/50">
      <div 
        className="h-full rounded-full transition-all duration-700 ease-out"
        style={{ width: `${value * 100}%`, backgroundColor: color }}
      />
    </div>
  </div>
);

// Hand distribution chart
const HandDistribution: React.FC<{ distribution: Record<string, number> }> = ({ distribution }) => {
  const handOrder = [
    'Royal Flush', 'Straight Flush', 'Four of a Kind', 'Full House',
    'Flush', 'Straight', 'Three of a Kind', 'Two Pair', 'One Pair', 'High Card'
  ];

  const maxValue = Math.max(...Object.values(distribution), 0.01);

  return (
    <div className="space-y-3.5">
      <h3 className="text-sm font-semibold text-slate-300 tracking-tight">Hand Distribution</h3>
      <div className="space-y-2.5">
        {handOrder.map(hand => {
          const value = distribution[hand] || 0;
          return (
            <div key={hand} className="grid grid-cols-[130px_1fr_60px] items-center gap-2.5 text-xs">
              <span className="text-slate-400 tracking-tight">{hand}</span>
              <div className="h-2 bg-slate-800/60 rounded-full overflow-hidden border border-slate-700/50">
                <div 
                  className="h-full bg-gradient-to-r from-slate-500 to-slate-400 rounded-full transition-all duration-700"
                  style={{ width: `${(value / maxValue) * 100}%` }}
                />
              </div>
              <span className="text-right text-slate-400" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{(value * 100).toFixed(2)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const SimulatorPage: React.FC = () => {
  const [gameState, setGameState] = useState<GameState>({
    player_hand: [],
    community_cards: [],
    opponent_count: 1
  });
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [simCount, setSimCount] = useState(10000);

  const API_URL = 'http://localhost:5001';

  const dealNewHand = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/deal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opponent_count: gameState.opponent_count })
      });
      const data = await res.json();
      setGameState(prev => ({
        ...prev,
        player_hand: data.player_hand,
        community_cards: []
      }));
      setSimulation(null);
    } catch (err) {
      console.error('Failed to deal:', err);
    }
    setLoading(false);
  };

  const dealCommunityCards = async (count: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/community`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_cards: gameState.community_cards,
          player_hand: gameState.player_hand,
          count
        })
      });
      const data = await res.json();
      setGameState(prev => ({
        ...prev,
        community_cards: data.community_cards
      }));
    } catch (err) {
      console.error('Failed to deal community:', err);
    }
    setLoading(false);
  };

  const runSimulation = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_hand: gameState.player_hand,
          community_cards: gameState.community_cards,
          opponent_count: gameState.opponent_count,
          num_simulations: simCount
        })
      });
      const data = await res.json();
      setSimulation(data);
    } catch (err) {
      console.error('Simulation failed:', err);
    }
    setLoading(false);
  };

  const communityStage = gameState.community_cards.length === 0 ? 'preflop' :
    gameState.community_cards.length === 3 ? 'flop' :
    gameState.community_cards.length === 4 ? 'turn' : 'river';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-7">
      <div className="space-y-6">
        {/* Poker Table */}
        <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700/60 p-7 shadow-2xl">
          <div className="bg-gradient-to-br from-green-800 via-green-900 to-green-950 rounded-[6rem] p-10 border-4 border-green-950/80 shadow-inner relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(16,185,129,0.1),transparent_50%)]"></div>
            <div className="space-y-14 relative z-10">
              {/* Community Cards */}
              <div className="flex flex-col items-center gap-5">
                <span className="text-xs uppercase tracking-widest text-green-100/90 font-semibold">Community Cards</span>
                <div className="flex gap-3.5">
                  {[0, 1, 2, 3, 4].map(i => (
                    <CardDisplay 
                      key={i} 
                      card={gameState.community_cards[i] || null}
                      faceDown={!gameState.community_cards[i]}
                    />
                  ))}
                </div>
              </div>

              {/* Player Hand */}
              <div className="flex flex-col items-center gap-5">
                <span className="text-xs uppercase tracking-widest text-green-100/90 font-semibold">Hole Cards</span>
                <div className="flex gap-3.5">
                  {gameState.player_hand.length > 0 ? (
                    gameState.player_hand.map((card, i) => (
                      <CardDisplay key={i} card={card} />
                    ))
                  ) : (
                    <>
                      <CardDisplay card={null} faceDown />
                      <CardDisplay card={null} faceDown />
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700/60 p-7 space-y-7 shadow-2xl">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="space-y-2.5">
              <Label htmlFor="opponent-count" className="text-sm font-medium text-slate-300">Number of Opponents</Label>
              <Input
                id="opponent-count"
                type="number"
                min={1}
                max={10}
                value={gameState.opponent_count}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  if (!isNaN(val) && val >= 1 && val <= 10) {
                    setGameState(prev => ({ ...prev, opponent_count: val }));
                  }
                }}
                style={{ fontFamily: 'IBM Plex Mono, monospace' }}
              />
            </div>

            <div className="space-y-2.5">
              <Label htmlFor="simulations" className="text-sm font-medium text-slate-300">Simulations</Label>
              <Select value={simCount.toString()} onValueChange={(value) => setSimCount(parseInt(value))}>
                <SelectTrigger id="simulations">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1000">1,000</SelectItem>
                  <SelectItem value="10000">10,000</SelectItem>
                  <SelectItem value="50000">50,000</SelectItem>
                  <SelectItem value="100000">100,000</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap gap-2.5 pt-2">
            <Button onClick={dealNewHand} disabled={loading} type="button" className="font-medium">
              Deal New Hand
            </Button>

            {communityStage === 'preflop' && gameState.player_hand.length > 0 && (
              <Button onClick={() => dealCommunityCards(3)} disabled={loading} variant="secondary" type="button" className="font-medium">
                Deal Flop
              </Button>
            )}
            {communityStage === 'flop' && (
              <Button onClick={() => dealCommunityCards(1)} disabled={loading} variant="secondary" type="button" className="font-medium">
                Deal Turn
              </Button>
            )}
            {communityStage === 'turn' && (
              <Button onClick={() => dealCommunityCards(1)} disabled={loading} variant="secondary" type="button" className="font-medium">
                Deal River
              </Button>
            )}

            <Button 
              onClick={runSimulation}
              disabled={loading || gameState.player_hand.length === 0}
              variant="default"
              type="button"
              className="font-medium bg-slate-100 hover:bg-slate-400"
            >
              {loading ? 'Running...' : 'Run Simulation'}
            </Button>
          </div>
        </div>
      </div>

      {/* Results Panel */}
      <div>
        <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700/60 p-7 sticky top-6 shadow-2xl">
          <h2 className="text-base font-bold text-slate-100 mb-5 pb-5 border-b border-slate-700/70 tracking-tight">
            Results
          </h2>

          {simulation ? (
            <div className="space-y-7">
              <div className="space-y-4">
                <ProbabilityBar label="Win" value={simulation.win_probability} color="#22c55e" />
                <ProbabilityBar label="Tie" value={simulation.tie_probability} color="#f59e0b" />
                <ProbabilityBar label="Lose" value={simulation.loss_probability} color="#ef4444" />
              </div>

              <div className="pt-5 border-t border-slate-700/70 space-y-1.5">
                <p className="text-xs text-slate-400 text-center tracking-tight" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>
                  {simulation.simulations_run.toLocaleString()} simulations
                </p>
                <p className="text-xs text-slate-400 text-center tracking-tight">
                  vs {gameState.opponent_count} opponent{gameState.opponent_count > 1 ? 's' : ''}
                </p>
              </div>

              <div className="pt-5 border-t border-slate-700/70">
                <HandDistribution distribution={simulation.hand_distribution} />
              </div>
            </div>
          ) : (
            <div className="text-center py-16 text-slate-400 text-sm space-y-2">
              <p className="text-slate-500">Deal a hand and run a simulation</p>
              <p className="text-slate-600">to view win probabilities</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

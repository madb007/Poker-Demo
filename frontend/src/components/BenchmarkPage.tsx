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

interface BenchmarkResult {
  method: string;
  num_hands: number;
  num_players: number;
  valid_hands: number;
  elapsed_time: number;
  hands_per_second: number;
  sample_hands: any[];
}

export const BenchmarkPage: React.FC = () => {
  const [method, setMethod] = useState<'pokerkit' | 'pyro'>('pokerkit');
  const [numHands, setNumHands] = useState(1000);
  const [numPlayers, setNumPlayers] = useState(2);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BenchmarkResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const API_URL = 'http://localhost:5001';

  const runBenchmark = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/benchmark`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          method,
          num_hands: numHands,
          num_players: numPlayers,
        })
      });
      
      if (!res.ok) {
        throw new Error('Benchmark failed');
      }
      
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
    
    setLoading(false);
  };

  return (
    <div className="space-y-7">
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700/60 p-7 shadow-2xl">
        <h2 className="text-lg font-bold text-slate-100 mb-6 tracking-tight">Configuration</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-7">
          <div className="space-y-2.5">
            <Label htmlFor="method" className="text-sm font-medium text-slate-300">Generation Method</Label>
            <Select value={method} onValueChange={(value) => setMethod(value as 'pokerkit' | 'pyro')}>
              <SelectTrigger id="method">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pokerkit">PokerKit</SelectItem>
                <SelectItem value="pyro">Pyro (Probabilistic)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2.5">
            <Label htmlFor="num-hands" className="text-sm font-medium text-slate-300">Number of Hands</Label>
            <Input
              id="num-hands"
              type="text"
              inputMode="numeric"
              placeholder="1-100000"
              value={numHands}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                if (!isNaN(val) && val >= 1 && val <= 100000) {
                  setNumHands(val);
                } else if (e.target.value === '') {
                  setNumHands(1);
                }
              }}
              style={{ fontFamily: 'IBM Plex Mono, monospace' }}
            />
          </div>

          <div className="space-y-2.5">
            <Label htmlFor="num-players" className="text-sm font-medium text-slate-300">Players per Hand</Label>
            <Input
              id="num-players"
              type="text"
              inputMode="numeric"
              placeholder="1-9"
              value={numPlayers}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                if (!isNaN(val) && val >= 1 && val <= 9) {
                  setNumPlayers(val);
                } else if (e.target.value === '') {
                  setNumPlayers(1);
                }
              }}
              style={{ fontFamily: 'IBM Plex Mono, monospace' }}
            />
          </div>
        </div>

        <Button onClick={runBenchmark} disabled={loading} className="w-full font-medium bg-slate-100 hover:bg-slate-400">
          {loading ? 'Running Benchmark...' : 'Run Benchmark'}
        </Button>
      </div>

      {error && (
        <div className="bg-red-950/30 border border-red-800/50 rounded-2xl p-5 backdrop-blur-sm shadow-lg">
          <p className="text-red-400 text-sm tracking-tight">Error: {error}</p>
        </div>
      )}

      {result && (
        <div className="space-y-7">
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700/60 p-7 shadow-2xl">
            <h2 className="text-lg font-bold text-slate-100 mb-6 tracking-tight">Results</h2>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-7">
              <div className="bg-slate-900/50 rounded-xl p-5 backdrop-blur-sm border border-slate-700/40">
                <div className="text-xs text-slate-400 mb-2 tracking-tight">Method</div>
                <div className="text-lg font-bold text-slate-100 uppercase tracking-tight">{result.method}</div>
              </div>
              
              <div className="bg-slate-900/50 rounded-xl p-5 backdrop-blur-sm border border-slate-700/40">
                <div className="text-xs text-slate-400 mb-2 tracking-tight">Valid Hands</div>
                <div className="text-lg font-bold text-green-400" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{result.valid_hands.toLocaleString()}</div>
              </div>
              
              <div className="bg-slate-900/50 rounded-xl p-5 backdrop-blur-sm border border-slate-700/40">
                <div className="text-xs text-slate-400 mb-2 tracking-tight">Elapsed Time</div>
                <div className="text-lg font-bold text-blue-400" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{result.elapsed_time.toFixed(4)}s</div>
              </div>
              
              <div className="bg-slate-900/50 rounded-xl p-5 backdrop-blur-sm border border-slate-700/40">
                <div className="text-xs text-slate-400 mb-2 tracking-tight">Hands/Second</div>
                <div className="text-lg font-bold text-purple-400" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{Math.round(result.hands_per_second).toLocaleString()}</div>
              </div>
            </div>

            <div className="bg-slate-900/50 rounded-xl p-5 backdrop-blur-sm border border-slate-700/40">
              <h3 className="text-sm font-semibold text-slate-300 mb-4 tracking-tight">Sample Hands</h3>
              <div className="space-y-5">
                {result.sample_hands.slice(0, 3).map((hand, idx) => (
                  <div key={idx} className="border-t border-slate-700/50 pt-4 first:border-t-0 first:pt-0">
                    <div className="text-xs text-slate-500 mb-2.5 tracking-tight" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>Hand {idx + 1}</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs" style={{ fontFamily: 'IBM Plex Mono, monospace' }}>
                      <div>
                        <span className="text-slate-400">Players: </span>
                        {hand.player_hands.map((ph: any[], pidx: number) => (
                          <div key={pidx} className="text-slate-300 ml-2 mt-1">
                            P{pidx + 1}: {ph.map(c => `${c.rank}${c.suit[0].toUpperCase()}`).join(', ')}
                          </div>
                        ))}
                      </div>
                      <div>
                        <span className="text-slate-400">Community: </span>
                        <span className="text-slate-300">
                          {hand.community.map((c: any) => `${c.rank}${c.suit[0].toUpperCase()}`).join(', ')}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

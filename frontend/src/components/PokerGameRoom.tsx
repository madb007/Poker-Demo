import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { io, Socket } from 'socket.io-client';

// Types
interface Card {
  rank: string;
  suit: string;
}

interface Player {
  id: number;
  name: string;
  player_type?: 'human' | 'demo' | 'llm';
  chips: number;
  hole_cards: Card[];
  is_dealer: boolean;
  is_small_blind: boolean;
  is_big_blind: boolean;
  is_active: boolean;
  current_bet: number;
  folded: boolean;
}

interface GameState {
  game_id: string;
  community_cards: Card[];
  pot: number;
  current_bet: number;
  players: Player[];
  current_player_index: number;
  game_stage: 'pre_flop' | 'flop' | 'turn' | 'river' | 'showdown' | 'waiting';
  small_blind: number;
  big_blind: number;
}

// Card Display Component
const CardDisplay: React.FC<{ card: Card | null; faceDown?: boolean }> = ({ card, faceDown }) => {
  const suitSymbols: Record<string, string> = {
    hearts: '♥',
    diamonds: '♦',
    clubs: '♣',
    spades: '♠'
  };

  const suitColors: Record<string, string> = {
    hearts: 'text-red-500',
    diamonds: 'text-red-500',
    clubs: 'text-black',
    spades: 'text-black'
  };

  if (faceDown || !card) {
    return (
      <div className="w-16 h-24 bg-gradient-to-br from-blue-600 to-blue-800 rounded border-2 border-blue-900 flex items-center justify-center">
        <div className="text-2xl text-blue-300">♠</div>
      </div>
    );
  }

  return (
    <div className="w-16 h-24 bg-white rounded border-2 border-gray-300 flex flex-col items-center justify-center">
      <div className={`text-lg font-bold ${suitColors[card.suit]}`}>
        {card.rank}
      </div>
      <div className={`text-2xl ${suitColors[card.suit]}`}>
        {suitSymbols[card.suit]}
      </div>
    </div>
  );
};

// Player Seat Component
const PlayerSeat: React.FC<{ player: Player; isCurrentPlayer: boolean; position: number; viewerPlayerId: number | null; totalActivePlayers: number; positionClass?: string }> = ({
  player,
  isCurrentPlayer,
  position,
  viewerPlayerId,
  totalActivePlayers,
  positionClass
}) => {
  // Calculate relative position from viewer's perspective
  let relativePosition = position;
  if (viewerPlayerId !== null && totalActivePlayers > 0) {
    relativePosition = (position - viewerPlayerId + totalActivePlayers) % totalActivePlayers;
  }

  // Map relative position to screen position based on player count
  let screenPositions: string[];
  
  if (totalActivePlayers === 2) {
    // Heads-up: one on left, one on right for better spacing around table boundary
    screenPositions = [
      'top-1/2 -translate-y-1/2 left-2',       // opponent (left)
      'top-1/2 -translate-y-1/2 right-2',      // viewer (right)
    ];
  } else {
    // Multi-way: distribute around table
    screenPositions = [
      'top-0 left-1/2 -translate-x-1/2',        // opposite (top)
      'top-1/4 right-2',                        // top right
      'bottom-1/4 right-2',                     // bottom right
      'bottom-0 left-1/2 -translate-x-1/2',     // bottom (viewer)
      'bottom-1/4 left-2',                      // bottom left
      'top-1/4 left-2'                          // top left
    ];
  }

  const finalPositionClass = positionClass || screenPositions[relativePosition] || 'bottom-0 left-1/2 -translate-x-1/2';

  return (
    <div className={`absolute ${finalPositionClass} w-32 ${isCurrentPlayer ? 'ring-4 ring-yellow-400' : ''}`}>
      <div className="bg-slate-700 rounded-lg p-3 text-center border-2 border-slate-600">
        <div className="text-sm font-bold text-slate-100 truncate">{player.name}</div>
        <div className="text-xs text-slate-300 mt-1">💰 ${player.chips}</div>
        {player.current_bet > 0 && (
          <div className="text-xs text-yellow-400 font-bold mt-1">Bet: ${player.current_bet}</div>
        )}
        {player.folded && (
          <div className="text-xs text-red-400 font-bold mt-1">FOLDED</div>
        )}
        {player.is_dealer && (
          <div className="text-xs text-green-400 font-bold mt-1">Dealer</div>
        )}
        {player.is_small_blind && (
          <div className="text-xs text-orange-400 font-bold mt-1">Small Blind</div>
        )}
        {player.is_big_blind && (
          <div className="text-xs text-orange-400 font-bold mt-1">Big Blind</div>
        )}
        
        {/* Hole Cards - only show for active non-folded players */}
        {player.is_active && !player.folded && (
          <div className="flex gap-1 justify-center mt-2">
            {player.hole_cards.map((card, idx) => (
              <div key={idx} className="scale-75 origin-top">
                <CardDisplay card={card} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export const PokerGameRoom: React.FC = () => {
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [playerName, setPlayerName] = useState('Player1');
  const [gameId, setGameId] = useState<string | null>(null);
  const [playerId, setPlayerId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [raiseAmount, setRaiseAmount] = useState(0);
  const [joined, setJoined] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [screen, setScreen] = useState<'landing' | 'create' | 'join' | 'game'>('landing');
  const [numPlayers, setNumPlayers] = useState(6);
  const [startingChips, setStartingChips] = useState(1000);
  const [smallBlind, setSmallBlind] = useState(5);
  const [bigBlind, setBigBlind] = useState(10);
  const [joinGameId, setJoinGameId] = useState('');
  const [llmOnline, setLlmOnline] = useState<boolean | null>(null);
  const socketRef = useRef<Socket | null>(null);

  const API_URL = 'http://localhost:5001';

  // Initialize WebSocket connection
  useEffect(() => {
    socketRef.current = io(API_URL);

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  // Poll LLM health status
  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_URL}/llm/health`);
        if (!isMounted) return;
        setLlmOnline(res.ok);
      } catch {
        if (isMounted) {
          setLlmOnline(false);
        }
      }
    };

    checkHealth();
    const timer = setInterval(checkHealth, 5000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, []);

  // Listen for game updates via WebSocket
  useEffect(() => {
    if (!socketRef.current) return;

    const socket = socketRef.current;

    // Listen for player ID assignment
    socket.on('player_assigned', (data) => {
      console.log('Player assigned:', data);
      setPlayerId(data.player_id);
    });

    // Listen for player joined events
    socket.on('player_joined', (data) => {
      console.log('Player joined event:', data);
      setGameState(data.game_state);
      // If player_id is present in event, set it
      if (typeof data.player_id === 'number') {
        setPlayerId(data.player_id);
      }
    });

    // Listen for game state updates
    socket.on('game_state_update', (data) => {
      console.log('Game state update:', data);
      if (data.game_state) {
        setGameState(data.game_state);
      }
    });

    // Listen for player connected
    socket.on('player_connected', (data) => {
      console.log('Player connected:', data);
    });

    // Listen for game actions
    socket.on('game_action', (data) => {
      console.log('Game action:', data);
      if (data.game_state) {
        setGameState(data.game_state);
      }
    });

    // Listen for errors
    socket.on('error', (data) => {
      console.error('Socket error:', data);
      setError(data.message || 'Socket error');
    });

    return () => {
      socket.off('player_assigned');
      socket.off('player_joined');
      socket.off('game_state_update');
      socket.off('player_connected');
      socket.off('game_action');
      socket.off('error');
    };
  }, []);

  // Create a new game
  const createNewGame = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/game/new`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_name: playerName || 'Dealer',
          num_players: numPlayers,
          starting_chips: startingChips,
          small_blind: smallBlind,
          big_blind: bigBlind
        })
      });

      if (res.ok) {
        const data = await res.json();
        setGameState(data);
        setGameId(data.game_id);
        setJoined(true);
        setScreen('game');

        // Join WebSocket room with player_id from response
        if (socketRef.current) {
          socketRef.current.emit('join_game_room', {
            game_id: data.game_id,
            player_name: playerName || 'Dealer',
            player_id: data.player_id
          });
        }
      } else {
        setError('Failed to create game');
      }
    } catch (error) {
      console.error('Failed to create game:', error);
      setError('Failed to create game');
    } finally {
      setLoading(false);
    }
  };

  // Join existing game
  const joinExistingGame = async () => {
    if (!joinGameId.trim()) {
      setError('Please enter a game ID');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/game/${joinGameId}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!res.ok) {
        setError('Game not found');
        setLoading(false);
        return;
      }

      const joinRes = await fetch(`${API_URL}/game/${joinGameId}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_name: playerName || 'Player'
        })
      });

      if (joinRes.ok) {
        const data = await joinRes.json();
        setGameState(data);
        setGameId(joinGameId);
        setJoined(true);
        setScreen('game');
        // Always set playerId from backend response
        if (typeof data.player_id === 'number') {
          setPlayerId(data.player_id);
        }
        // Join WebSocket room AFTER getting player_id from HTTP response
        if (socketRef.current) {
          socketRef.current.emit('join_game_room', {
            game_id: joinGameId,
            player_name: playerName || 'Player',
            player_id: data.player_id
          });
        }
      } else {
        const errorData = await joinRes.json();
        setError(errorData.error || 'Failed to join game');
      }
    } catch (error) {
      console.error('Failed to join game:', error);
      setError('Failed to join game');
    } finally {
      setLoading(false);
    }
  };

  // Deal next hand
  const dealNextHand = async () => {
    if (!gameState) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/game/${gameState.game_id}/deal`, {
        method: 'POST'
      });

      if (res.ok) {
        const data = await res.json();
        setGameState(data);
      }
    } catch (error) {
      console.error('Failed to deal hand:', error);
    } finally {
      setLoading(false);
    }
  };

  // Player actions
  const fold = async () => {
    if (!gameState || playerId === null) {
      setError('Waiting for player ID assignment...');
      return;
    }
    await playerAction('fold');
  };

  const check = async () => {
    if (!gameState || playerId === null) {
      setError('Waiting for player ID assignment...');
      return;
    }
    await playerAction('check');
  };

  const call = async () => {
    if (!gameState || playerId === null) {
      setError('Waiting for player ID assignment...');
      return;
    }
    await playerAction('call');
  };

  const raise = async () => {
    if (!gameState || playerId === null) {
      setError('Waiting for player ID assignment...');
      return;
    }
    await playerAction('raise', raiseAmount);
  };

  const playerAction = async (action: string, amount?: number) => {
    if (!gameState || playerId === null) {
      setError('Player ID not assigned yet');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/game/${gameState.game_id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_id: playerId,
          action,
          amount: amount || 0
        })
      });
      if (!res.ok) {
        const errorData = await res.json();
        setError(errorData.error || `Action failed: ${action}`);
      }
      // Do not fetch game state via HTTP; rely on WebSocket events for updates
    } catch (error) {
      console.error('Action failed:', error);
      setError('Action failed');
    } finally {
      setLoading(false);
    }
  };

  if (screen === 'landing') {
    return (
      <div className="h-full flex items-center justify-center bg-slate-900 p-4">
        <div className="bg-slate-800 rounded-lg p-8 border border-slate-700 max-w-md w-full text-center">
          <h1 className="text-4xl font-bold text-slate-100 mb-2">
            Poker
          </h1>
          <p className="text-slate-400 mb-8">
            Texas Hold'em Simulator
          </p>

          <div className="space-y-3">
            <Button
              onClick={() => setScreen('create')}
              className="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-6 text-lg"
            >
              Create New Table
            </Button>

            <Button
              onClick={() => {
                setError(null);
                setScreen('join');
              }}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-6 text-lg"
            >
              Join Existing Game
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === 'create') {
    return (
      <div className="h-full flex items-center justify-center bg-slate-900 p-4">
        <div className="bg-slate-800 rounded-lg p-8 border border-slate-700 max-w-md w-full">
          <h2 className="text-2xl font-bold text-slate-100 mb-6 text-center">
            Create Poker Table
          </h2>

          {error && (
            <div className="bg-red-900 border border-red-700 text-red-100 px-3 py-2 rounded mb-4 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <Label htmlFor="playerName" className="text-slate-300">
                Your Name
              </Label>
              <Input
                id="playerName"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                className="mt-2 bg-slate-700 border-slate-600 text-slate-100"
                placeholder="Enter your name"
              />
            </div>

            <div>
              <Label htmlFor="numPlayers" className="text-slate-300">
                Number of Players: {numPlayers}
              </Label>
              <input
                id="numPlayers"
                type="range"
                min="2"
                max="9"
                value={numPlayers}
                onChange={(e) => setNumPlayers(parseInt(e.target.value))}
                className="mt-2 w-full"
              />
            </div>

            <div>
              <Label htmlFor="startingChips" className="text-slate-300">
                Starting Chips
              </Label>
              <Input
                id="startingChips"
                type="number"
                value={startingChips}
                onChange={(e) => setStartingChips(parseInt(e.target.value) || 1000)}
                className="mt-2 bg-slate-700 border-slate-600 text-slate-100"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="smallBlind" className="text-slate-300">
                  Small Blind
                </Label>
                <Input
                  id="smallBlind"
                  type="number"
                  value={smallBlind}
                  onChange={(e) => setSmallBlind(parseInt(e.target.value) || 5)}
                  className="mt-2 bg-slate-700 border-slate-600 text-slate-100"
                />
              </div>
              <div>
                <Label htmlFor="bigBlind" className="text-slate-300">
                  Big Blind
                </Label>
                <Input
                  id="bigBlind"
                  type="number"
                  value={bigBlind}
                  onChange={(e) => setBigBlind(parseInt(e.target.value) || 10)}
                  className="mt-2 bg-slate-700 border-slate-600 text-slate-100"
                />
              </div>
            </div>

            <Button
              onClick={createNewGame}
              disabled={loading}
              className="w-full bg-green-600 hover:bg-green-700 text-white font-bold"
            >
              {loading ? 'Creating Table...' : 'Create Table'}
            </Button>

            <Button
              onClick={() => setScreen('landing')}
              disabled={loading}
              className="w-full bg-slate-600 hover:bg-slate-700 text-white"
            >
              Back
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === 'join') {
    return (
      <div className="h-full flex items-center justify-center bg-slate-900 p-4">
        <div className="bg-slate-800 rounded-lg p-8 border border-slate-700 max-w-md w-full">
          <h2 className="text-2xl font-bold text-slate-100 mb-6 text-center">
            Join Poker Game
          </h2>

          {error && (
            <div className="bg-red-900 border border-red-700 text-red-100 px-3 py-2 rounded mb-4 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <Label htmlFor="joinPlayerName" className="text-slate-300">
                Your Name
              </Label>
              <Input
                id="joinPlayerName"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                className="mt-2 bg-slate-700 border-slate-600 text-slate-100"
                placeholder="Enter your name"
              />
            </div>

            <div>
              <Label htmlFor="gameIdInput" className="text-slate-300">
                Game ID
              </Label>
              <Input
                id="gameIdInput"
                value={joinGameId}
                onChange={(e) => setJoinGameId(e.target.value)}
                className="mt-2 bg-slate-700 border-slate-600 text-slate-100 font-mono text-sm"
                placeholder="Paste game ID here"
              />
            </div>

            <Button
              onClick={joinExistingGame}
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold"
            >
              {loading ? 'Joining Game...' : 'Join Game'}
            </Button>

            <Button
              onClick={() => setScreen('landing')}
              disabled={loading}
              className="w-full bg-slate-600 hover:bg-slate-700 text-white"
            >
              Back
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === 'game') {
    if (!gameState) {
      return <div className="h-full flex items-center justify-center text-slate-100 bg-slate-900">Loading...</div>;
    }

    // Only consider players who are active
    const activePlayers = gameState.players.filter(p => p.is_active);
    const totalActivePlayers = activePlayers.length;

    // Find the current player
    const currentPlayer = (gameState.current_player_index >= 0 && gameState.players[gameState.current_player_index])
      ? gameState.players[gameState.current_player_index]
      : null;

    // Find viewer's own player object
    const viewerPlayer = (playerId !== null && gameState.players[playerId]) ? gameState.players[playerId] : null;
    const playerTypeCounts = gameState.players.reduce(
      (acc, player) => {
        if (player.player_type === 'demo') acc.demo += 1;
        else if (player.player_type === 'llm') acc.llm += 1;
        else acc.human += 1;
        return acc;
      },
      { human: 0, demo: 0, llm: 0 }
    );

    return (
      <div className="h-full bg-gradient-to-b from-green-900 to-green-800 flex flex-col p-2">
        {/* Debug Info */}
        <div className="bg-slate-900 text-xs text-yellow-300 rounded p-2 mb-2">
          <div>Debug Info:</div>
          <div>playerId: {playerId !== null ? playerId : 'N/A'}</div>
          <div>current_player_index: {gameState.current_player_index}</div>
          <div>current player name: {gameState.players[gameState.current_player_index]?.name || 'N/A'}</div>
        </div>
        {/* Table Info */}
        <div className="bg-slate-800 rounded-lg p-2 border border-slate-700 mb-2 text-xs">
          <div className="grid grid-cols-5 gap-4 text-center">
            <div>
              <div className="text-xs text-slate-400">Game Stage</div>
              <div className="text-sm font-bold text-slate-100 capitalize">
                {gameState.game_stage}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Pot</div>
              <div className="text-lg font-bold text-yellow-400">
                ${gameState.pot}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Current Bet</div>
              <div className="text-sm font-bold text-slate-100">
                ${gameState.current_bet}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Small/Big Blind</div>
              <div className="text-sm font-bold text-slate-100">
                ${gameState.small_blind}/{gameState.big_blind}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Active Players</div>
              <div className="text-sm font-bold text-slate-100">
                {activePlayers.filter(p => !p.folded).length}
              </div>
            </div>
          </div>
        </div>

        {/* Game ID Display */}
        <div className="bg-slate-800 rounded-lg p-2 border border-slate-700 mb-2 text-xs">
          <p className="text-xs text-slate-400">Game ID (Share to invite)</p>
          <p className="text-sm font-mono text-slate-100 break-all">{gameState.game_id}</p>
        </div>

        {/* Bot Status Panel */}
        <div className="bg-slate-800 rounded-lg p-2 border border-slate-700 mb-2 text-xs">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs text-slate-400">Bot Status</div>
            <div className="flex items-center gap-2">
              <Badge variant={llmOnline ? "llm" : "default"}>
                <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${llmOnline ? "bg-emerald-400" : "bg-slate-500"}`} />
                LLM {llmOnline === null ? "checking" : llmOnline ? "online" : "offline"}
              </Badge>
              <Badge variant="human">Human {playerTypeCounts.human}</Badge>
              <Badge variant="demo">Demo {playerTypeCounts.demo}</Badge>
              <Badge variant="llm">LLM {playerTypeCounts.llm}</Badge>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {gameState.players.map((player) => (
              <div key={player.id} className="flex items-center gap-1.5 text-slate-300">
                <Badge
                  variant={
                    player.player_type === 'demo'
                      ? 'demo'
                      : player.player_type === 'llm'
                        ? 'llm'
                        : 'human'
                  }
                >
                  {player.player_type ?? 'human'}
                </Badge>
                <span className="text-xs">{player.name}</span>
                {!player.is_active && <span className="text-slate-500">(inactive)</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Table - Relative Container */}
        <div className="flex-1 relative bg-green-700 rounded-full border-8 border-green-900 mb-2 min-h-[700px] max-h-[900px] min-w-[700px] max-w-[900px] mx-auto" style={{ aspectRatio: '1/1' }}>
          {/* Community Cards */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
            <div className="text-xs text-slate-200 font-bold mb-2">
              Community
            </div>
            <div className="flex gap-2 mb-4">
              {gameState.community_cards.map((card, idx) => (
                <CardDisplay key={idx} card={card} />
              ))}
            </div>
          </div>

          {/* Player Seats (viewer and others) */}
          {(() => {
            // Custom positions for 3 players
            const threeHandedPositions = [
              'top-[10%] left-1/2 -translate-x-1/2', // Top middle (viewer)
              'bottom-[10%] left-[15%]', // Bottom left
              'bottom-[10%] right-[15%]' // Bottom right
            ];
            // Viewer seat first
            let seats = [];
            if (viewerPlayer && viewerPlayer.is_active) {
              seats.push(
                <PlayerSeat
                  key={viewerPlayer.id}
                  player={viewerPlayer}
                  isCurrentPlayer={gameState.current_player_index === viewerPlayer.id}
                  position={0}
                  viewerPlayerId={0}
                  totalActivePlayers={totalActivePlayers}
                  positionClass={threeHandedPositions[0]}
                />
              );
            }
            // Other seats
            activePlayers
              .filter(player => !(viewerPlayer && player.id === viewerPlayer.id))
              .forEach((player, idx) => {
                let viewerActiveIdx = null;
                if (playerId !== null && gameState.players[playerId]?.is_active) {
                  viewerActiveIdx = gameState.players.slice(0, playerId + 1).filter(p => p.is_active).length - 1;
                }
                let positionClass = undefined;
                if (totalActivePlayers === 3) {
                  positionClass = threeHandedPositions[idx + 1];
                }
                seats.push(
                  <PlayerSeat
                    key={player.id}
                    player={{ ...player, hole_cards: [] }} // Hide other players' cards
                    isCurrentPlayer={gameState.current_player_index === player.id}
                    position={idx + 1}
                    viewerPlayerId={viewerActiveIdx}
                    totalActivePlayers={totalActivePlayers}
                    positionClass={positionClass}
                  />
                );
              });
            return seats;
          })()}
        </div>

        {/* Control Panel */}
        <div className="bg-slate-800 rounded-lg p-2 border border-slate-700 text-xs">
          {currentPlayer && gameState.current_player_index === playerId ? (
            <>
              <div className="text-sm text-slate-300 mb-4">
                Your turn! You have ${currentPlayer.chips} chips
              </div>

              <div className="flex gap-2 mb-4">
                <Button
                  onClick={fold}
                  disabled={loading || playerId === null}
                  className="flex-1 bg-red-600 hover:bg-red-700"
                >
                  Fold
                </Button>
                <Button
                  onClick={check}
                  disabled={loading || playerId === null || gameState.current_bet > currentPlayer.current_bet}
                  className="flex-1 bg-gray-600 hover:bg-gray-700"
                >
                  Check
                </Button>
                <Button
                  onClick={call}
                  disabled={loading || playerId === null || currentPlayer.current_bet >= gameState.current_bet}
                  className="flex-1 bg-blue-600 hover:bg-blue-700"
                >
                  Call {gameState.current_bet - currentPlayer.current_bet}
                </Button>
                <Button
                  onClick={raise}
                  disabled={loading || playerId === null}
                  className="flex-1 bg-yellow-600 hover:bg-yellow-700"
                >
                  Raise
                </Button>
              </div>

              <div className="flex gap-2">
                <Input
                  type="number"
                  value={raiseAmount || ''}
                  onChange={(e) => setRaiseAmount(parseInt(e.target.value) || 0)}
                  className="flex-1 bg-slate-700 border-slate-600 text-slate-100"
                  placeholder="Enter raise amount"
                />
                <Button
                  onClick={raise}
                  disabled={loading || playerId === null || raiseAmount === 0}
                  className="bg-yellow-600 hover:bg-yellow-700 whitespace-nowrap"
                >
                  Raise {raiseAmount || 0}
                </Button>
              </div>
            </>
          ) : (
            <div className="text-sm text-slate-300">
              Waiting for {currentPlayer?.name ? currentPlayer.name : 'next player'}'s action...
            </div>
          )}

          <Button
            onClick={dealNextHand}
            disabled={loading || gameState.game_stage !== 'showdown'}
            className="w-full mt-4 bg-green-600 hover:bg-green-700"
          >
            {gameState.game_stage === 'showdown' ? 'Deal Next Hand' : 'Game in Progress'}
          </Button>
        </div>
      </div>
    );
  }
};

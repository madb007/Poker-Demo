import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { SimulatorPage } from '@/components/SimulatorPage';
import { BenchmarkPage } from '@/components/BenchmarkPage';
import { PokerGameRoom } from '@/components/PokerGameRoom';
import '@/styles/globals.css';

const API_URL = 'http://localhost:5001';

const App: React.FC = () => {
  const [connected, setConnected] = useState(false);
  const location = useLocation();

  // Force dark mode on mount
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  // Check backend connection
  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then(res => res.json())
      .then(() => setConnected(true))
      .catch(() => setConnected(false));
  }, []);

  return (
    <div className="h-screen overflow-hidden bg-slate-900 flex flex-col">
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="text-center flex-1">
              <h1 className="text-3xl font-bold text-slate-100">Poker Simulator</h1>
              <div className="mt-2 text-xs">
                <span className={`inline-flex items-center gap-1.5 ${connected ? 'text-green-400' : 'text-red-400'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`}></span>
                  {connected ? 'Backend Connected' : 'Backend Offline'}
                </span>
              </div>
            </div>
          </div>
          
          <nav className="mt-4 flex gap-4 justify-center">
            <Link 
              to="/" 
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                location.pathname === '/' 
                  ? 'bg-slate-100 text-slate-900' 
                  : 'text-slate-300 hover:text-slate-100 hover:bg-slate-700'
              }`}
            >
              Simulator
            </Link>
            <Link 
              to="/game" 
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                location.pathname === '/game' 
                  ? 'bg-slate-100 text-slate-900' 
                  : 'text-slate-300 hover:text-slate-100 hover:bg-slate-700'
              }`}
            >
              Game Room
            </Link>
            <Link 
              to="/benchmark" 
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                location.pathname === '/benchmark' 
                  ? 'bg-slate-100 text-slate-900' 
                  : 'text-slate-300 hover:text-slate-100 hover:bg-slate-700'
              }`}
            >
              Benchmark
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/" element={<SimulatorPage />} />
            <Route path="/game" element={<PokerGameRoom />} />
            <Route path="/benchmark" element={<BenchmarkPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
};

// Mount app
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

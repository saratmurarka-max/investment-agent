import { useState } from "react";
import AddHoldings from "./components/AddHoldings";
import Chat from "./components/Chat";
import Portfolio from "./components/Portfolio";

const DEMO_CLIENT_ID = 1;
const DEMO_PORTFOLIO_ID = 1;

export default function App() {
  const [portfolioId] = useState<number>(DEMO_PORTFOLIO_ID);
  const [refreshKey, setRefreshKey] = useState(0);

  function handleHoldingAdded() {
    setRefreshKey((k) => k + 1); // triggers Portfolio to re-fetch
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top nav */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Investment Agent</h1>
          <p className="text-xs text-gray-400">Client #{DEMO_CLIENT_ID}</p>
        </div>
        <span className="text-xs bg-yellow-100 text-yellow-800 px-2.5 py-1 rounded-full font-medium">
          Demo Mode
        </span>
      </header>

      {/* Main layout */}
      <main className="max-w-7xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-73px)]">
        {/* Left: Holdings + Add Holdings */}
        <div className="lg:col-span-1 space-y-4 overflow-y-auto">
          <Portfolio portfolioId={portfolioId} refreshKey={refreshKey} />
          <AddHoldings portfolioId={portfolioId} onAdded={handleHoldingAdded} />
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-xs text-yellow-700">
            <strong>Disclaimer:</strong> This tool provides informational analysis only.
            It is not personalized investment advice. Consult a licensed financial advisor
            before making investment decisions.
          </div>
        </div>

        {/* Right: Chat */}
        <div className="lg:col-span-2">
          <Chat portfolioId={portfolioId} />
        </div>
      </main>
    </div>
  );
}

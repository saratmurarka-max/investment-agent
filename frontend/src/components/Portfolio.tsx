import { useEffect, useState } from "react";
import { getPortfolio } from "../api/client";

interface Holding {
  ticker: string;
  shares: number;
  avg_cost: number;
}

interface PortfolioData {
  id: number;
  name: string;
  currency: string;
  holdings: Holding[];
}

interface Props {
  portfolioId: number;
  refreshKey?: number; // increment to force a reload
}

export default function Portfolio({ portfolioId, refreshKey }: Props) {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    getPortfolio(portfolioId)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [portfolioId, refreshKey]);

  if (error) return <p className="text-red-500 text-sm">{error}</p>;
  if (!data) return <p className="text-sm text-gray-400 animate-pulse">Loading holdings...</p>;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 className="font-semibold text-gray-800 mb-4">{data.name}</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-100">
              <th className="pb-2 font-medium">Ticker</th>
              <th className="pb-2 font-medium text-right">Shares</th>
              <th className="pb-2 font-medium text-right">Avg Cost</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => (
              <tr key={h.ticker} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="py-2.5 font-mono font-medium text-blue-700">{h.ticker}</td>
                <td className="py-2.5 text-right text-gray-600">{h.shares.toFixed(4)}</td>
                <td className="py-2.5 text-right text-gray-600">${h.avg_cost.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.holdings.length === 0 && (
          <p className="text-gray-400 text-sm text-center py-6">No holdings yet.</p>
        )}
      </div>
    </div>
  );
}

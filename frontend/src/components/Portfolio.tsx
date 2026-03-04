import { useEffect, useState } from "react";
import { getPortfolio, deleteHolding } from "../api/client";

interface Holding {
  id: number;
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
  refreshKey?: number;
}

export default function Portfolio({ portfolioId, refreshKey }: Props) {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    setError(null);
    getPortfolio(portfolioId)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [portfolioId, refreshKey]);

  async function handleDelete(holding: Holding) {
    if (!confirm(`Delete ${holding.ticker} from portfolio?`)) return;
    setDeletingId(holding.id);
    try {
      await deleteHolding(portfolioId, holding.id);
      setData((prev) =>
        prev
          ? { ...prev, holdings: prev.holdings.filter((h) => h.id !== holding.id) }
          : prev
      );
    } catch (e: any) {
      alert(e.message ?? "Failed to delete holding");
    } finally {
      setDeletingId(null);
    }
  }

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
              <th className="pb-2 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => (
              <tr key={h.id} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="py-2.5 font-mono font-medium text-blue-700">{h.ticker}</td>
                <td className="py-2.5 text-right text-gray-600">{h.shares.toFixed(4)}</td>
                <td className="py-2.5 text-right text-gray-600">${h.avg_cost.toFixed(2)}</td>
                <td className="py-2.5 text-right">
                  <button
                    onClick={() => handleDelete(h)}
                    disabled={deletingId === h.id}
                    className="text-red-400 hover:text-red-600 disabled:opacity-40 transition-colors text-xs px-2 py-1 rounded hover:bg-red-50"
                    title="Delete holding"
                  >
                    {deletingId === h.id ? "..." : "Delete"}
                  </button>
                </td>
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

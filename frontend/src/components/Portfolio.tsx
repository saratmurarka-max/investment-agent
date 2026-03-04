import { useEffect, useRef, useState } from "react";
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

const MAX_RETRIES = 8;
const RETRY_DELAY_MS = 4000;

export default function Portfolio({ portfolioId, refreshKey }: Props) {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (retryTimer.current) clearTimeout(retryTimer.current);
    setError(null);
    setRetryCount(0);
    load(0);

    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, [portfolioId, refreshKey]);

  function load(attempt: number) {
    getPortfolio(portfolioId)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if (attempt < MAX_RETRIES) {
          setRetryCount(attempt + 1);
          retryTimer.current = setTimeout(() => load(attempt + 1), RETRY_DELAY_MS);
        } else {
          setError(e.message ?? "Failed to load portfolio");
        }
      });
  }

  function manualRetry() {
    setError(null);
    setRetryCount(0);
    load(0);
  }

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

  if (error) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 text-center">
        <p className="text-red-500 text-sm mb-3">{error}</p>
        <button
          onClick={manualRetry}
          className="text-xs bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 text-center">
        <p className="text-sm text-gray-400 animate-pulse">
          {retryCount === 0
            ? "Loading holdings..."
            : `Connecting to server... (${retryCount}/${MAX_RETRIES})`}
        </p>
        {retryCount > 0 && (
          <p className="text-xs text-gray-300 mt-1">Server is waking up, please wait</p>
        )}
      </div>
    );
  }

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
                <td className="py-2.5 text-right text-gray-600">₹{h.avg_cost.toFixed(2)}</td>
                <td className="py-2.5 text-right">
                  <button
                    onClick={() => handleDelete(h)}
                    disabled={deletingId === h.id}
                    className="text-red-400 hover:text-red-600 disabled:opacity-40 transition-colors text-xs px-2 py-1 rounded hover:bg-red-50"
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

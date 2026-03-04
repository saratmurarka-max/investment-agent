import { useEffect, useRef, useState } from "react";
import { getPortfolio, getPortfolioPnL, deleteHolding } from "../api/client";

interface Holding {
  id: number;
  ticker: string;
  shares: number;
  avg_cost: number;
  current_price?: number;
  invested?: number;
  current_value?: number;
  unrealized_gain?: number;
  unrealized_pct?: number;
}

interface Summary {
  total_invested: number;
  total_current_value: number;
  total_unrealized_gain: number;
  total_unrealized_pct: number;
  total_realized_gain: number;
  total_short_term_gain: number;
  total_long_term_gain: number;
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

function fmt(n: number) {
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Strip exchange suffix (.NS / .BO) for clean Indian-market-style display */
function displayTicker(ticker: string) {
  return ticker.replace(/\.(NS|BO)$/i, "");
}

function PnLBadge({ value, pct }: { value: number; pct?: number }) {
  const pos = value >= 0;
  return (
    <span className={`font-medium ${pos ? "text-green-600" : "text-red-500"}`}>
      {pos ? "+" : ""}{fmt(value)}
      {pct !== undefined && (
        <span className="text-xs ml-1 opacity-80">
          ({pos ? "+" : ""}{pct.toFixed(2)}%)
        </span>
      )}
    </span>
  );
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3 text-center">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className="text-sm font-semibold text-gray-800">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Portfolio({ portfolioId, refreshKey }: Props) {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [pnlLoading, setPnlLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (retryTimer.current) clearTimeout(retryTimer.current);
    setError(null);
    setRetryCount(0);
    setSummary(null);
    loadPortfolio(0);
    return () => { if (retryTimer.current) clearTimeout(retryTimer.current); };
  }, [portfolioId, refreshKey]);

  function loadPortfolio(attempt: number) {
    getPortfolio(portfolioId)
      .then((d) => {
        setData(d);
        setError(null);
        // Auto-load P&L after holdings are loaded
        loadPnL(d.holdings);
      })
      .catch(() => {
        if (attempt < MAX_RETRIES) {
          setRetryCount(attempt + 1);
          retryTimer.current = setTimeout(() => loadPortfolio(attempt + 1), RETRY_DELAY_MS);
        } else {
          setError("Could not connect to server. Please refresh.");
        }
      });
  }

  function loadPnL(holdings: Holding[]) {
    if (!holdings || holdings.length === 0) return;
    setPnlLoading(true);
    getPortfolioPnL(portfolioId)
      .then((pnlData) => {
        // Merge P&L data into holdings by id
        const pnlMap = new Map(pnlData.holdings.map((h: Holding) => [h.id, h]));
        setData((prev) =>
          prev
            ? {
                ...prev,
                holdings: prev.holdings.map((h) => ({
                  ...h,
                  ...(pnlMap.get(h.id) as Holding ?? {}),
                })),
              }
            : prev
        );
        setSummary(pnlData.summary);
      })
      .catch(() => {
        // P&L fetch failed silently — holdings still show without live prices
      })
      .finally(() => setPnlLoading(false));
  }

  function manualRetry() {
    setError(null);
    setRetryCount(0);
    loadPortfolio(0);
  }

  function refreshPnL() {
    if (data) loadPnL(data.holdings);
  }

  async function handleDelete(holding: Holding) {
    if (!confirm(`Delete ${holding.ticker} from portfolio?`)) return;
    setDeletingId(holding.id);
    try {
      await deleteHolding(portfolioId, holding.id);
      setData((prev) =>
        prev ? { ...prev, holdings: prev.holdings.filter((h) => h.id !== holding.id) } : prev
      );
      setSummary(null);
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
        <button onClick={manualRetry} className="text-xs bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700">
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 text-center">
        <p className="text-sm text-gray-400 animate-pulse">
          {retryCount === 0 ? "Loading holdings..." : `Connecting to server... (${retryCount}/${MAX_RETRIES})`}
        </p>
        {retryCount > 0 && <p className="text-xs text-gray-300 mt-1">Server is waking up, please wait</p>}
      </div>
    );
  }

  const hasLivePrices = data.holdings.some((h) => h.current_price !== undefined && h.current_price! > 0);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-800">{data.name}</h2>
        <button
          onClick={refreshPnL}
          disabled={pnlLoading}
          className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-40 flex items-center gap-1"
        >
          {pnlLoading ? "Refreshing..." : "⟳ Refresh P&L"}
        </button>
      </div>

      {/* P&L Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 gap-2">
          <SummaryCard label="Total Invested" value={fmt(summary.total_invested)} />
          <SummaryCard
            label="Current Value"
            value={fmt(summary.total_current_value)}
            sub={summary.total_unrealized_gain >= 0
              ? `+${fmt(summary.total_unrealized_gain)} (${summary.total_unrealized_pct.toFixed(2)}%)`
              : `${fmt(summary.total_unrealized_gain)} (${summary.total_unrealized_pct.toFixed(2)}%)`}
          />
          {summary.total_realized_gain !== 0 && (
            <>
              <SummaryCard
                label="Realized Gain (STCG)"
                value={fmt(summary.total_short_term_gain)}
              />
              <SummaryCard
                label="Realized Gain (LTCG)"
                value={fmt(summary.total_long_term_gain)}
              />
            </>
          )}
        </div>
      )}

      {/* Holdings Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-100 text-xs">
              <th className="pb-2 font-medium">Ticker</th>
              <th className="pb-2 font-medium text-right">Shares</th>
              <th className="pb-2 font-medium text-right">Avg Buy</th>
              {hasLivePrices && (
                <>
                  <th className="pb-2 font-medium text-right">LTP</th>
                  <th className="pb-2 font-medium text-right">Value</th>
                  <th className="pb-2 font-medium text-right">Unrealized P&L</th>
                </>
              )}
              <th className="pb-2 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => (
              <tr key={h.id} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="py-2 font-mono font-medium text-blue-700 text-xs">{displayTicker(h.ticker)}</td>
                <td className="py-2 text-right text-gray-600 text-xs">{h.shares.toFixed(2)}</td>
                <td className="py-2 text-right text-gray-600 text-xs">{fmt(h.avg_cost)}</td>
                {hasLivePrices && (
                  <>
                    <td className="py-2 text-right text-gray-600 text-xs">
                      {h.current_price ? fmt(h.current_price) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="py-2 text-right text-gray-600 text-xs">
                      {h.current_value ? fmt(h.current_value) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="py-2 text-right text-xs">
                      {h.unrealized_gain !== undefined ? (
                        <PnLBadge value={h.unrealized_gain} pct={h.unrealized_pct} />
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </>
                )}
                <td className="py-2 text-right">
                  <button
                    onClick={() => handleDelete(h)}
                    disabled={deletingId === h.id}
                    className="text-red-400 hover:text-red-600 disabled:opacity-40 text-xs px-2 py-1 rounded hover:bg-red-50"
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

      {pnlLoading && !hasLivePrices && (
        <p className="text-xs text-gray-400 text-center animate-pulse">Fetching live prices...</p>
      )}
    </div>
  );
}

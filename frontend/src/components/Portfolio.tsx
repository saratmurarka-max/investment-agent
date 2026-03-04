import { useEffect, useRef, useState } from "react";
import { getPortfolio, getPortfolioPnL, deleteHolding } from "../api/client";
import PortfolioAnalytics from "./PortfolioAnalytics";

interface Holding {
  id: number;
  ticker: string;
  name?: string;
  shares: number;
  avg_cost: number;
  current_price?: number | null;
  invested?: number;
  current_value?: number | null;
  unrealized_gain?: number | null;
  unrealized_pct?: number | null;
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

function PnLBadge({ value, pct }: { value: number; pct?: number | null }) {
  const pos = value >= 0;
  return (
    <span className={`font-medium ${pos ? "text-green-600" : "text-red-500"}`}>
      {pos ? "+" : ""}{fmt(value)}
      {pct != null && (
        <span className="text-xs ml-1 opacity-80">
          ({pos ? "+" : ""}{pct.toFixed(2)}%)
        </span>
      )}
    </span>
  );
}

function SummaryCard({ label, value, sub, subColor }: {
  label: string;
  value: string;
  sub?: string;
  subColor?: "red" | "green" | "gray";
}) {
  const colorClass =
    subColor === "green" ? "text-green-600" :
    subColor === "red"   ? "text-red-500"   :
    "text-gray-400";
  return (
    <div className="bg-gray-50 rounded-lg p-3 text-center">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className="text-sm font-semibold text-gray-800">{value}</p>
      {sub && <p className={`text-xs mt-0.5 ${colorClass}`}>{sub}</p>}
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
  const [showAnalytics, setShowAnalytics] = useState(true);
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
    const label = holding.name || displayTicker(holding.ticker);
    if (!confirm(`Delete ${label} from portfolio?`)) return;
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

  const hasLivePrices = data.holdings.some((h) => h.current_price != null && h.current_price > 0);
  const missingLtp    = data.holdings.filter((h) => h.current_price == null || h.current_price === 0).length;
  const pricedCount   = data.holdings.length - missingLtp;

  const unrealizedGain   = summary?.total_unrealized_gain ?? 0;
  const unrealizedPct    = summary?.total_unrealized_pct  ?? 0;
  const unrealizedColor  = unrealizedGain >= 0 ? "green" : "red";
  const unrealizedSub    = `${unrealizedGain >= 0 ? "+" : ""}${fmt(unrealizedGain)} (${unrealizedPct >= 0 ? "+" : ""}${unrealizedPct.toFixed(2)}%)${missingLtp > 0 && pricedCount > 0 ? `*` : ""}`;

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
        <>
          <div className="grid grid-cols-2 gap-2">
            <SummaryCard
              label="Total Invested"
              value={fmt(summary.total_invested)}
              sub={`${data.holdings.length} holdings`}
              subColor="gray"
            />
            <SummaryCard
              label="Current Value"
              value={fmt(summary.total_current_value)}
              sub={unrealizedSub}
              subColor={unrealizedColor}
            />
            {summary.total_realized_gain !== 0 && (
              <>
                <SummaryCard
                  label="Realized Gain (STCG)"
                  value={fmt(summary.total_short_term_gain)}
                  subColor={summary.total_short_term_gain >= 0 ? "green" : "red"}
                />
                <SummaryCard
                  label="Realized Gain (LTCG)"
                  value={fmt(summary.total_long_term_gain)}
                  subColor={summary.total_long_term_gain >= 0 ? "green" : "red"}
                />
              </>
            )}
          </div>
          {missingLtp > 0 && pricedCount > 0 && (
            <p className="text-xs text-amber-500">
              * {missingLtp} holding{missingLtp > 1 ? "s" : ""} without live price counted at cost (break-even). Current Value % reflects only priced holdings.
            </p>
          )}
        </>
      )}

      {/* Analytics Panel */}
      {summary && data.holdings.some((h) => h.current_price != null) && (
        <div>
          <button
            onClick={() => setShowAnalytics((v) => !v)}
            className="w-full flex items-center justify-between text-xs text-gray-500 hover:text-gray-700 py-2 border-t border-gray-100"
          >
            <span className="font-semibold uppercase tracking-wide">
              {showAnalytics ? "▲ Hide Analytics" : "▼ Show Analytics"}
            </span>
          </button>
          {showAnalytics && (
            <div className="pt-2">
              <PortfolioAnalytics holdings={data.holdings} summary={summary} />
            </div>
          )}
        </div>
      )}

      {/* Holdings Table */}
      <div className="overflow-x-auto border-t border-gray-100 pt-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-100 text-xs">
              <th className="pb-2 font-medium">Stock</th>
              <th className="pb-2 font-medium text-right">Qty</th>
              <th className="pb-2 font-medium text-right">Avg Cost</th>
              {hasLivePrices && (
                <>
                  <th className="pb-2 font-medium text-right">LTP</th>
                  <th className="pb-2 font-medium text-right">Value</th>
                  <th className="pb-2 font-medium text-right">Unrealized P&amp;L</th>
                </>
              )}
              <th className="pb-2 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => {
              const hasPrice = h.current_price != null && h.current_price > 0;
              return (
                <tr key={h.id} className="border-b border-gray-50 hover:bg-gray-50">
                  {/* Stock name */}
                  <td className="py-2 font-medium text-blue-700 text-xs">
                    {h.name ? (
                      <span title={displayTicker(h.ticker)}>{h.name}</span>
                    ) : (
                      <span className="font-mono">{displayTicker(h.ticker)}</span>
                    )}
                  </td>

                  {/* Qty */}
                  <td className="py-2 text-right text-gray-600 text-xs">{h.shares.toFixed(0)}</td>

                  {/* Avg Cost */}
                  <td className="py-2 text-right text-gray-600 text-xs">{fmt(h.avg_cost)}</td>

                  {hasLivePrices && (
                    <>
                      {/* LTP */}
                      <td className="py-2 text-right text-gray-600 text-xs">
                        {hasPrice
                          ? fmt(h.current_price!)
                          : <span className="text-gray-300">—</span>}
                      </td>

                      {/* Value = qty × LTP */}
                      <td className="py-2 text-right text-gray-600 text-xs">
                        {hasPrice && h.current_value != null
                          ? fmt(h.current_value)
                          : <span className="text-gray-300">—</span>}
                      </td>

                      {/* Unrealized P&L */}
                      <td className="py-2 text-right text-xs">
                        {hasPrice && h.unrealized_gain != null
                          ? <PnLBadge value={h.unrealized_gain} pct={h.unrealized_pct} />
                          : <span className="text-gray-300">—</span>}
                      </td>
                    </>
                  )}

                  {/* Delete */}
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
              );
            })}
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

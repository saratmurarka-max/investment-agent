import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getDerivativesPnL } from "../api/client";

interface MonthData {
  month: string;
  pnl: number;
  profit: number;
  loss: number;
  trades: number;
}

interface OptionTypeData {
  type: string;
  pnl: number;
  trades: number;
}

interface TradeInfo {
  scrip_symbol: string;
  option_type: string | null;
  underlying: string | null;
  strike_price: number | null;
  trade_date: string | null;
  buy_qty: number;
  buy_rate: number;
  sell_rate: number;
  booked_pnl: number;
}

interface DerivativePnL {
  total_trades: number;
  total_booked_pnl: number;
  total_profit: number;
  total_loss: number;
  winning_trades: number;
  losing_trades: number;
  by_month: MonthData[];
  by_option_type: OptionTypeData[];
  best_trade: TradeInfo | null;
  worst_trade: TradeInfo | null;
}

interface Props {
  portfolioId: number;
}

function fmtInr(n: number) {
  const abs = Math.abs(n);
  let str: string;
  if (abs >= 100000) {
    str = "₹" + (n / 100000).toFixed(2) + "L";
  } else if (abs >= 1000) {
    str = "₹" + (n / 1000).toFixed(1) + "k";
  } else {
    str = "₹" + n.toFixed(2);
  }
  return str;
}

function fmtFull(n: number) {
  return (n >= 0 ? "+" : "") + "₹" + Math.abs(n).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtMonth(m: string): string {
  const [yr, mo] = m.split("-");
  const names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const idx = parseInt(mo) - 1;
  return `${names[idx] ?? mo}-${yr.slice(2)}`;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const val: number = payload[0].value;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-md px-3 py-2 text-xs">
      <p className="font-semibold text-gray-700 mb-1">{label}</p>
      <p className={val >= 0 ? "text-green-600" : "text-red-500"}>
        Net P&L: {fmtFull(val)}
      </p>
      {payload[0]?.payload?.trades != null && (
        <p className="text-gray-400">{payload[0].payload.trades} trades</p>
      )}
    </div>
  );
};

export default function DerivativesView({ portfolioId }: Props) {
  const [data, setData] = useState<DerivativePnL | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getDerivativesPnL(portfolioId)
      .then(setData)
      .catch(() => setError("Failed to load derivatives data."))
      .finally(() => setLoading(false));
  }, [portfolioId]);

  if (loading) {
    return <p className="text-xs text-gray-400 text-center py-4 animate-pulse">Loading F&O data...</p>;
  }
  if (error) {
    return <p className="text-xs text-red-500 text-center py-4">{error}</p>;
  }
  if (!data || data.total_trades === 0) {
    return (
      <p className="text-xs text-gray-400 text-center py-6">
        No derivative trades found. Upload a DER P&L file from the Derivatives tab.
      </p>
    );
  }

  const winRate = data.total_trades > 0
    ? Math.round((data.winning_trades / data.total_trades) * 100)
    : 0;

  const chartData = data.by_month.map((m) => ({
    label: fmtMonth(m.month),
    pnl:   m.pnl,
    trades: m.trades,
  }));

  const netColor = data.total_booked_pnl >= 0 ? "text-green-600" : "text-red-500";
  const netBg    = data.total_booked_pnl >= 0 ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200";

  return (
    <div className="space-y-4">
      {/* ── Summary Cards ── */}
      <div className="grid grid-cols-2 gap-2">
        {/* Net P&L */}
        <div className={`col-span-2 border rounded-xl p-3 text-center ${netBg}`}>
          <p className="text-xs text-gray-500 mb-0.5">Net F&O P&L (All Trades)</p>
          <p className={`text-xl font-bold ${netColor}`}>
            {fmtFull(data.total_booked_pnl)}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">{data.total_trades} trades</p>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">Gross Profit</p>
          <p className="text-base font-semibold text-green-600">
            +₹{data.total_profit.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </p>
          <p className="text-xs text-gray-400">{data.winning_trades} winners</p>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">Gross Loss</p>
          <p className="text-base font-semibold text-red-500">
            -₹{data.total_loss.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </p>
          <p className="text-xs text-gray-400">{data.losing_trades} losers</p>
        </div>
      </div>

      {/* ── Win Rate ── */}
      <div className="bg-gray-50 rounded-xl p-3">
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-gray-500 font-medium">Win Rate</span>
          <span className="font-semibold text-gray-700">{winRate}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="h-2 rounded-full bg-green-500 transition-all duration-500"
            style={{ width: `${winRate}%` }}
          />
        </div>
        <div className="flex justify-between text-xs mt-1 text-gray-400">
          <span>{data.winning_trades} winning</span>
          <span>{data.losing_trades} losing</span>
        </div>
      </div>

      {/* ── CE vs PE breakdown ── */}
      {data.by_option_type.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            CE vs PE Breakdown
          </p>
          <div className="grid grid-cols-2 gap-2">
            {data.by_option_type.map((ot) => {
              const isPos = ot.pnl >= 0;
              return (
                <div
                  key={ot.type}
                  className={`rounded-xl border p-3 text-center ${
                    isPos ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"
                  }`}
                >
                  <p className="text-xs font-bold text-gray-600 mb-0.5">
                    {ot.type === "CE" ? "CALL (CE)" : ot.type === "PE" ? "PUT (PE)" : ot.type}
                  </p>
                  <p className={`text-sm font-semibold ${isPos ? "text-green-600" : "text-red-500"}`}>
                    {fmtFull(ot.pnl)}
                  </p>
                  <p className="text-xs text-gray-400">{ot.trades} trades</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Monthly P&L Chart ── */}
      {chartData.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Monthly Net P&L
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 20 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 9, fill: "#9ca3af" }}
                angle={-45}
                textAnchor="end"
                interval={0}
              />
              <YAxis
                tickFormatter={(v) => fmtInr(v)}
                tick={{ fontSize: 9, fill: "#9ca3af" }}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                {chartData.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={entry.pnl >= 0 ? "#16a34a" : "#dc2626"}
                    opacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Best & Worst Trade ── */}
      {(data.best_trade || data.worst_trade) && (
        <div className="grid grid-cols-1 gap-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Highlight Trades
          </p>
          {data.best_trade && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold text-green-700">Best Trade</span>
                <span className="text-xs font-semibold text-green-600">
                  {fmtFull(data.best_trade.booked_pnl)}
                </span>
              </div>
              <p className="text-xs text-gray-600 font-mono truncate">{data.best_trade.scrip_symbol}</p>
              <div className="flex gap-3 mt-1 text-xs text-gray-400">
                <span>{data.best_trade.trade_date ?? "—"}</span>
                <span>Qty: {data.best_trade.buy_qty}</span>
                <span>Buy: ₹{data.best_trade.buy_rate?.toFixed(2)}</span>
                <span>Sell: ₹{data.best_trade.sell_rate?.toFixed(2)}</span>
              </div>
            </div>
          )}
          {data.worst_trade && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold text-red-700">Worst Trade</span>
                <span className="text-xs font-semibold text-red-500">
                  {fmtFull(data.worst_trade.booked_pnl)}
                </span>
              </div>
              <p className="text-xs text-gray-600 font-mono truncate">{data.worst_trade.scrip_symbol}</p>
              <div className="flex gap-3 mt-1 text-xs text-gray-400">
                <span>{data.worst_trade.trade_date ?? "—"}</span>
                <span>Qty: {data.worst_trade.buy_qty}</span>
                <span>Buy: ₹{data.worst_trade.buy_rate?.toFixed(2)}</span>
                <span>Sell: ₹{data.worst_trade.sell_rate?.toFixed(2)}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Tax note ── */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">
        <p className="font-semibold mb-0.5">Tax Note — F&O Income</p>
        <p>
          F&O trading income is taxed as <strong>Business Income (PGBP)</strong> — non-speculative.
          File <strong>ITR-3</strong>. Losses can be carried forward for 8 years.
          Consult a CA before filing.
        </p>
      </div>
    </div>
  );
}

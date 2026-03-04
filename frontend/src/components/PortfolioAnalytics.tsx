import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

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

interface Props {
  holdings: Holding[];
  summary: Summary;
}

const PIE_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316",
  "#6366f1", "#14b8a6",
];

function fmtVal(n: number) {
  const abs = Math.abs(n);
  if (abs >= 10_000_000) return "₹" + (n / 10_000_000).toFixed(2) + " Cr";
  if (abs >= 100_000)    return "₹" + (n / 100_000).toFixed(2) + " L";
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function shortName(h: Holding, maxLen = 14): string {
  if (h.name) {
    const words = h.name.split(" ");
    let s = words[0];
    for (let i = 1; i < words.length; i++) {
      if ((s + " " + words[i]).length > maxLen) break;
      s += " " + words[i];
    }
    return s;
  }
  return h.ticker.replace(/\.(NS|BO)$/i, "").slice(0, maxLen);
}

// ── Custom tooltips ────────────────────────────────────────────────────────────

function DonutTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-md p-2 text-xs">
      <p className="font-semibold text-gray-700">{d.name}</p>
      <p className="text-gray-500 mt-0.5">
        {fmtVal(d.value)} · {d.pct.toFixed(1)}%
      </p>
    </div>
  );
}

function BarTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const v: number = payload[0].value;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-md p-2 text-xs">
      <p className="font-semibold text-gray-700">{label}</p>
      <p className={v >= 0 ? "text-green-600" : "text-red-500"}>
        {v >= 0 ? "+" : ""}
        {v.toFixed(1)}%
      </p>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PortfolioAnalytics({ holdings, summary }: Props) {
  const withPnl  = holdings.filter((h) => h.unrealized_pct != null);
  const priced   = holdings.filter((h) => h.current_value != null && h.current_value > 0);
  const winners  = withPnl.filter((h) => (h.unrealized_pct ?? 0) > 0).length;
  const losers   = withPnl.filter((h) => (h.unrealized_pct ?? 0) < 0).length;
  const noLtp    = holdings.length - withPnl.length;
  const total    = summary.total_current_value;
  const invested = summary.total_invested;
  const gainPct  = invested > 0 ? ((total - invested) / invested) * 100 : 0;

  // ── Donut: allocation by current value ──────────────────────────────────────
  const sorted8 = [...priced].sort((a, b) => (b.current_value ?? 0) - (a.current_value ?? 0));
  const top8    = sorted8.slice(0, 8);
  const rest    = sorted8.slice(8);
  const donutData = [
    ...top8.map((h) => ({
      name:  shortName(h),
      value: h.current_value ?? 0,
      pct:   total > 0 ? ((h.current_value ?? 0) / total) * 100 : 0,
    })),
    ...(rest.length > 0
      ? [{
          name:  `+${rest.length} others`,
          value: rest.reduce((s, h) => s + (h.current_value ?? 0), 0),
          pct:   total > 0
            ? (rest.reduce((s, h) => s + (h.current_value ?? 0), 0) / total) * 100
            : 0,
        }]
      : []),
  ];

  // ── Bar chart: top-5 gainers + bottom-5 losers ──────────────────────────────
  const byPct    = [...withPnl].sort((a, b) => (b.unrealized_pct ?? 0) - (a.unrealized_pct ?? 0));
  const seen     = new Set<number>();
  const barItems = [...byPct.slice(0, 5), ...byPct.slice(-5).reverse()].filter((h) => {
    if (seen.has(h.id)) return false;
    seen.add(h.id);
    return true;
  });
  const barData = barItems
    .map((h) => ({
      name: shortName(h, 12),
      pct:  Math.round((h.unrealized_pct ?? 0) * 10) / 10,
    }))
    .sort((a, b) => b.pct - a.pct);

  // ── Best / worst ─────────────────────────────────────────────────────────────
  const best  = byPct[0];
  const worst = byPct[byPct.length - 1];

  return (
    <div className="space-y-4">
      {/* ── Overview strip ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-green-50 rounded-xl p-3 border border-green-100">
          <p className="text-2xl font-bold text-green-600">{winners}</p>
          <p className="text-xs text-green-500 mt-0.5">Winners</p>
        </div>
        <div className="bg-red-50 rounded-xl p-3 border border-red-100">
          <p className="text-2xl font-bold text-red-500">{losers}</p>
          <p className="text-xs text-red-400 mt-0.5">Losers</p>
        </div>
        <div className="bg-amber-50 rounded-xl p-3 border border-amber-100">
          <p className="text-2xl font-bold text-amber-500">{noLtp}</p>
          <p className="text-xs text-amber-400 mt-0.5">No LTP</p>
        </div>
      </div>

      {/* ── Best / Worst highlight ───────────────────────────────────────────── */}
      {best && worst && (
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-green-50 border border-green-100 rounded-xl p-3">
            <p className="text-xs text-green-500 font-medium mb-1">Best Performer</p>
            <p className="text-xs text-green-700 font-semibold truncate">{shortName(best, 18)}</p>
            <p className="text-sm font-bold text-green-600 mt-0.5">
              +{(best.unrealized_pct ?? 0).toFixed(1)}%
            </p>
            <p className="text-xs text-green-500">
              +{fmtVal(best.unrealized_gain ?? 0)}
            </p>
          </div>
          <div className="bg-red-50 border border-red-100 rounded-xl p-3">
            <p className="text-xs text-red-400 font-medium mb-1">Worst Performer</p>
            <p className="text-xs text-red-600 font-semibold truncate">{shortName(worst, 18)}</p>
            <p className="text-sm font-bold text-red-500 mt-0.5">
              {(worst.unrealized_pct ?? 0).toFixed(1)}%
            </p>
            <p className="text-xs text-red-400">
              {fmtVal(worst.unrealized_gain ?? 0)}
            </p>
          </div>
        </div>
      )}

      {/* ── Portfolio health bar ─────────────────────────────────────────────── */}
      <div className="bg-gray-50 rounded-xl p-4">
        <div className="flex justify-between items-center mb-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Portfolio Health</p>
          <span className={`text-xs font-bold ${gainPct >= 0 ? "text-green-600" : "text-red-500"}`}>
            {gainPct >= 0 ? "+" : ""}{gainPct.toFixed(2)}% overall
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="text-green-600 font-medium">{winners} ▲</span>
          <div className="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden flex">
            <div
              className="h-full bg-green-400 rounded-l-full transition-all"
              style={{ width: `${(winners / Math.max(winners + losers, 1)) * 100}%` }}
            />
            <div
              className="h-full bg-red-400 rounded-r-full transition-all"
              style={{ width: `${(losers / Math.max(winners + losers, 1)) * 100}%` }}
            />
          </div>
          <span className="text-red-400 font-medium">{losers} ▼</span>
        </div>
        <div className="flex justify-between mt-2 text-xs">
          <span className="text-gray-400">Invested: {fmtVal(invested)}</span>
          <span className={gainPct >= 0 ? "text-green-600" : "text-red-500"}>
            Current: {fmtVal(total)}
          </span>
        </div>
      </div>

      {/* ── Donut: allocation ────────────────────────────────────────────────── */}
      {donutData.length > 0 && (
        <div className="bg-gray-50 rounded-xl p-4">
          <p className="text-xs font-semibold text-gray-500 mb-3 uppercase tracking-wide">
            Portfolio Allocation
          </p>
          <div className="flex items-center gap-4">
            {/* Chart */}
            <div className="flex-shrink-0" style={{ width: 150, height: 150 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={donutData}
                    cx="50%"
                    cy="50%"
                    innerRadius={42}
                    outerRadius={68}
                    dataKey="value"
                    strokeWidth={2}
                    stroke="#f9fafb"
                  >
                    {donutData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* Legend */}
            <div className="flex-1 space-y-1.5 min-w-0">
              {donutData.map((item, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs">
                  <span
                    className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                    style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                  />
                  <span className="text-gray-600 truncate flex-1 min-w-0">{item.name}</span>
                  <span className="text-gray-400 font-medium tabular-nums ml-1">
                    {item.pct.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Bar chart: top gainers & losers ─────────────────────────────────── */}
      {barData.length > 0 && (
        <div className="bg-gray-50 rounded-xl p-4">
          <p className="text-xs font-semibold text-gray-500 mb-3 uppercase tracking-wide">
            Top Gainers &amp; Losers
          </p>
          <ResponsiveContainer width="100%" height={barData.length * 30 + 24}>
            <BarChart
              data={barData}
              layout="vertical"
              margin={{ left: 4, right: 36, top: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
              <XAxis
                type="number"
                tickFormatter={(v) => v + "%"}
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 10, fill: "#6b7280" }}
                width={76}
                axisLine={false}
                tickLine={false}
              />
              <ReferenceLine x={0} stroke="#d1d5db" strokeWidth={1.5} />
              <Tooltip content={<BarTooltip />} />
              <Bar dataKey="pct" radius={[0, 4, 4, 0]} maxBarSize={16}>
                {barData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.pct >= 0 ? "#10b981" : "#ef4444"}
                    fillOpacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

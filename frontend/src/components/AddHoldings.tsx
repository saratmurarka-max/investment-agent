import { useEffect, useRef, useState } from "react";
import {
  type StockResult,
  addHolding,
  clearAllHoldings,
  clearDerivatives,
  downloadTaxReport,
  searchStocks,
  uploadDerivativesExcel,
  uploadHoldingsExcel,
} from "../api/client";

interface Props {
  portfolioId: number;
  onAdded: () => void;
}

type Tab = "manual" | "excel" | "derivatives" | "clear";

const TAB_LABELS: Record<Tab, string> = {
  manual:      "Manual Entry",
  excel:       "Upload Excel",
  derivatives: "Derivatives",
  clear:       "Clear All",
};

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function AddHoldings({ portfolioId, onAdded }: Props) {
  const [tab, setTab] = useState<Tab>("manual");

  // --- Manual form ---
  const [tickerInput, setTickerInput] = useState("");
  const [selectedStock, setSelectedStock] = useState<StockResult | null>(null);
  const [suggestions, setSuggestions] = useState<StockResult[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [shares, setShares] = useState("");
  const [avgCost, setAvgCost] = useState("");
  const [manualLoading, setManualLoading] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const debouncedQuery = useDebounce(tickerInput, 250);

  useEffect(() => {
    if (!debouncedQuery || selectedStock) {
      setSuggestions([]);
      return;
    }
    searchStocks(debouncedQuery, 8).then((results) => {
      setSuggestions(results);
      setShowDropdown(results.length > 0);
    });
  }, [debouncedQuery, selectedStock]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  function handleSelectStock(stock: StockResult) {
    setSelectedStock(stock);
    setTickerInput(`${stock.symbol} — ${stock.name}`);
    setSuggestions([]);
    setShowDropdown(false);
  }

  function handleTickerClear() {
    setSelectedStock(null);
    setTickerInput("");
    setSuggestions([]);
  }

  async function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    setManualError(null);
    setManualSuccess(null);

    const ticker = selectedStock?.ticker ?? tickerInput.trim().toUpperCase();
    const sharesNum = parseFloat(shares);
    const costNum = parseFloat(avgCost);

    if (!ticker) { setManualError("Please select or enter a stock."); return; }
    if (isNaN(sharesNum) || sharesNum <= 0) { setManualError("Shares must be > 0."); return; }
    if (isNaN(costNum) || costNum <= 0) { setManualError("Avg cost must be > 0."); return; }

    setManualLoading(true);
    try {
      await addHolding(portfolioId, { ticker, shares: sharesNum, avg_cost: costNum });
      const label = selectedStock ? selectedStock.symbol : ticker;
      setManualSuccess(`${label} added successfully.`);
      setSelectedStock(null);
      setTickerInput(""); setShares(""); setAvgCost("");
      onAdded();
    } catch (err: unknown) {
      setManualError(err instanceof Error ? err.message : "Failed to add holding.");
    } finally {
      setManualLoading(false);
    }
  }

  // --- Tax report download ---
  const [taxLoading, setTaxLoading] = useState(false);
  const [taxError, setTaxError] = useState<string | null>(null);

  async function handleTaxDownload() {
    setTaxError(null);
    setTaxLoading(true);
    try {
      await downloadTaxReport(portfolioId);
    } catch (err: unknown) {
      setTaxError(err instanceof Error ? err.message : "Failed to generate report.");
    } finally {
      setTaxLoading(false);
    }
  }

  // --- Equity Excel upload ---
  const [dragOver, setDragOver] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<{
    added: number; tickers: string[]; skipped: string[];
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleEquityFile(file: File) {
    setUploadError(null);
    setUploadResult(null);
    if (!file.name.endsWith(".xlsx")) {
      setUploadError("Only .xlsx files are supported.");
      return;
    }
    setUploadLoading(true);
    try {
      const result = await uploadHoldingsExcel(portfolioId, file);
      setUploadResult(result);
      onAdded();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploadLoading(false);
    }
  }

  // --- Derivatives upload ---
  const [derivDragOver, setDerivDragOver] = useState(false);
  const [derivLoading, setDerivLoading] = useState(false);
  const [derivError, setDerivError] = useState<string | null>(null);
  const [derivResult, setDerivResult] = useState<{
    imported: number; skipped: string[];
  } | null>(null);
  const [clearDerivLoading, setClearDerivLoading] = useState(false);
  const [clearDerivMsg, setClearDerivMsg] = useState<string | null>(null);
  const derivFileRef = useRef<HTMLInputElement>(null);

  async function handleDerivFile(file: File) {
    setDerivError(null);
    setDerivResult(null);
    setClearDerivMsg(null);
    if (!file.name.endsWith(".xlsx")) {
      setDerivError("Only .xlsx files are supported.");
      return;
    }
    setDerivLoading(true);
    try {
      const result = await uploadDerivativesExcel(portfolioId, file);
      setDerivResult(result);
      onAdded();
    } catch (err: unknown) {
      setDerivError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setDerivLoading(false);
    }
  }

  async function handleClearDerivatives() {
    if (!confirm("Delete ALL derivative trades from this portfolio? This cannot be undone.")) return;
    setClearDerivLoading(true);
    setClearDerivMsg(null);
    setDerivError(null);
    try {
      const r = await clearDerivatives(portfolioId);
      setClearDerivMsg(`Cleared ${r.deleted} derivative trade${r.deleted !== 1 ? "s" : ""}.`);
      onAdded();
    } catch (err: unknown) {
      setDerivError(err instanceof Error ? err.message : "Failed to clear derivatives.");
    } finally {
      setClearDerivLoading(false);
    }
  }

  // --- Clear all holdings ---
  const [clearLoading, setClearLoading] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);
  const [clearMsg, setClearMsg] = useState<string | null>(null);

  async function handleClearAll() {
    if (!confirm(
      "Delete ALL equity holdings and realized P&L from this portfolio?\n\n" +
      "This cannot be undone. You can re-upload your broker file afterwards."
    )) return;
    setClearLoading(true);
    setClearError(null);
    setClearMsg(null);
    try {
      const r = await clearAllHoldings(portfolioId);
      setClearMsg(`Cleared ${r.deleted_holdings} holding${r.deleted_holdings !== 1 ? "s" : ""}.`);
      onAdded();
    } catch (err: unknown) {
      setClearError(err instanceof Error ? err.message : "Failed to clear holdings.");
    } finally {
      setClearLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 className="font-semibold text-gray-800 mb-4">Add Holdings</h2>

      {/* Tabs — 4 tabs in 2×2 grid */}
      <div className="grid grid-cols-2 gap-1 mb-5 bg-gray-100 rounded-lg p-1">
        {(["manual", "excel", "derivatives", "clear"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`py-1.5 text-xs font-medium rounded-md transition-colors ${
              tab === t ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
            } ${t === "clear" ? "text-red-500 hover:text-red-700" : ""}`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {/* ── Manual Entry ── */}
      {tab === "manual" && (
        <form onSubmit={handleManualSubmit} className="space-y-3">
          <div ref={dropdownRef} className="relative">
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Stock Name / Symbol
            </label>
            <div className="flex gap-1">
              <input
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Search e.g. Reliance or INFY"
                value={tickerInput}
                onChange={(e) => {
                  setTickerInput(e.target.value);
                  if (selectedStock) setSelectedStock(null);
                }}
                onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
                autoComplete="off"
              />
              {selectedStock && (
                <button
                  type="button"
                  onClick={handleTickerClear}
                  className="px-2 text-gray-400 hover:text-gray-700 text-xl leading-none"
                  title="Clear"
                >
                  ×
                </button>
              )}
            </div>

            {showDropdown && suggestions.length > 0 && (
              <ul className="absolute z-20 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                {suggestions.map((s) => (
                  <li
                    key={s.ticker}
                    onMouseDown={() => handleSelectStock(s)}
                    className="flex items-center justify-between px-3 py-2.5 hover:bg-blue-50 cursor-pointer"
                  >
                    <span>
                      <span className="font-mono font-semibold text-blue-700 text-sm mr-2">
                        {s.symbol}
                      </span>
                      <span className="text-gray-500 text-xs">{s.name}</span>
                    </span>
                    <span className="text-gray-300 text-xs ml-2 shrink-0">.NS</span>
                  </li>
                ))}
              </ul>
            )}

            {selectedStock && (
              <p className="text-xs text-green-600 mt-1">
                Ticker: <span className="font-mono font-medium">{selectedStock.ticker}</span>
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Shares</label>
              <input
                type="number" min="0" step="any"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="10"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Avg Cost (₹)</label>
              <input
                type="number" min="0" step="any"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="2500.00"
                value={avgCost}
                onChange={(e) => setAvgCost(e.target.value)}
              />
            </div>
          </div>

          {manualError   && <p className="text-xs text-red-500">{manualError}</p>}
          {manualSuccess && <p className="text-xs text-green-600">{manualSuccess}</p>}

          <button
            type="submit"
            disabled={manualLoading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {manualLoading ? "Adding..." : "Add Stock"}
          </button>
        </form>
      )}

      {/* ── Equity Excel Upload ── */}
      {tab === "excel" && (
        <div className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault(); setDragOver(false);
              const f = e.dataTransfer.files[0];
              if (f) handleEquityFile(f);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
              dragOver
                ? "border-blue-400 bg-blue-50"
                : "border-gray-200 hover:border-blue-300 hover:bg-gray-50"
            }`}
          >
            <div className="text-3xl mb-2">📊</div>
            <p className="text-sm font-medium text-gray-700">
              {uploadLoading ? "Uploading..." : "Drop your Equity Excel file here"}
            </p>
            <p className="text-xs text-gray-400 mt-1">or click to browse — .xlsx only</p>
            <input
              ref={fileInputRef} type="file" accept=".xlsx" className="hidden"
              onChange={(e) => e.target.files?.[0] && handleEquityFile(e.target.files[0])}
            />
          </div>

          <div className="bg-blue-50 rounded-lg p-3 text-xs text-gray-500">
            <p className="font-medium text-gray-600 mb-1">Supported formats:</p>
            <ul className="list-disc list-inside space-y-0.5 text-gray-500">
              <li>PROFITMART Portfolio Report (auto-detected)</li>
              <li>Simple: Ticker | Shares | Avg Cost (row 1 = headers)</li>
            </ul>
            <p className="mt-1.5 text-amber-600 font-medium">
              Note: Replaces all existing equity holdings on upload.
            </p>
          </div>

          {uploadError && <p className="text-xs text-red-500">{uploadError}</p>}

          {uploadResult && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
              <p className="font-medium">Import complete</p>
              <p>
                {uploadResult.added} stock{uploadResult.added !== 1 ? "s" : ""} added:{" "}
                {uploadResult.tickers.slice(0, 8).join(", ")}
                {uploadResult.tickers.length > 8 ? ` +${uploadResult.tickers.length - 8} more` : ""}
              </p>
              {uploadResult.skipped.length > 0 && (
                <p className="text-yellow-600 mt-1">Skipped: {uploadResult.skipped.join(", ")}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Derivatives Upload ── */}
      {tab === "derivatives" && (
        <div className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDerivDragOver(true); }}
            onDragLeave={() => setDerivDragOver(false)}
            onDrop={(e) => {
              e.preventDefault(); setDerivDragOver(false);
              const f = e.dataTransfer.files[0];
              if (f) handleDerivFile(f);
            }}
            onClick={() => derivFileRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
              derivDragOver
                ? "border-purple-400 bg-purple-50"
                : "border-gray-200 hover:border-purple-300 hover:bg-gray-50"
            }`}
          >
            <div className="text-3xl mb-2">📈</div>
            <p className="text-sm font-medium text-gray-700">
              {derivLoading ? "Uploading..." : "Drop your Derivatives P&L Excel here"}
            </p>
            <p className="text-xs text-gray-400 mt-1">PROFITMART DER P&L format — .xlsx only</p>
            <input
              ref={derivFileRef} type="file" accept=".xlsx" className="hidden"
              onChange={(e) => e.target.files?.[0] && handleDerivFile(e.target.files[0])}
            />
          </div>

          <div className="bg-purple-50 rounded-lg p-3 text-xs text-gray-500">
            <p className="font-medium text-gray-600 mb-1">Expected format (PROFITMART DER P&L):</p>
            <ul className="list-disc list-inside space-y-0.5">
              <li>Rows 1–3: metadata (broker name, report title, date)</li>
              <li>Row 4: headers including <span className="font-mono">INSTRUMENT_TYPE</span>, <span className="font-mono">Booked P/L</span></li>
              <li>Scrip format: <span className="font-mono">IO CE NIFTY 02Dec2025 26600</span></li>
            </ul>
            <p className="mt-1.5 text-amber-600 font-medium">
              Note: Replaces all existing derivative trades on upload.
            </p>
          </div>

          {derivError && <p className="text-xs text-red-500">{derivError}</p>}
          {clearDerivMsg && <p className="text-xs text-green-600">{clearDerivMsg}</p>}

          {derivResult && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
              <p className="font-medium">Import complete</p>
              <p>{derivResult.imported} derivative trade{derivResult.imported !== 1 ? "s" : ""} imported.</p>
              {derivResult.skipped.length > 0 && (
                <p className="text-yellow-600 mt-1">Skipped: {derivResult.skipped.join(", ")}</p>
              )}
            </div>
          )}

          {/* Clear derivatives button */}
          <div className="border-t border-gray-100 pt-3">
            <button
              onClick={handleClearDerivatives}
              disabled={clearDerivLoading}
              className="w-full border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-40 py-2 rounded-lg text-xs font-medium transition-colors"
            >
              {clearDerivLoading ? "Clearing..." : "Clear All Derivative Trades"}
            </button>
          </div>
        </div>
      )}

      {/* ── Clear All Holdings ── */}
      {tab === "clear" && (
        <div className="space-y-4">
          <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <p className="text-sm font-semibold text-red-700 mb-1">Clear All Equity Holdings</p>
            <p className="text-xs text-red-600">
              This will permanently delete all equity holdings and realized P&L data
              from this portfolio. This action cannot be undone.
            </p>
          </div>

          <p className="text-xs text-gray-500 text-center">
            After clearing, you can upload a new broker file or add stocks manually.
          </p>

          {clearError && <p className="text-xs text-red-500 text-center">{clearError}</p>}
          {clearMsg && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700 text-center">
              <p className="font-medium">{clearMsg}</p>
              <p className="mt-0.5">You can now upload a new file or add stocks manually.</p>
            </div>
          )}

          <button
            onClick={handleClearAll}
            disabled={clearLoading}
            className="w-full bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            {clearLoading ? "Clearing..." : "Delete All Holdings"}
          </button>
        </div>
      )}

      {/* ── Tax Report Download ── */}
      <div className="mt-5 pt-4 border-t border-gray-100">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Tax Filing
        </p>
        <button
          onClick={handleTaxDownload}
          disabled={taxLoading}
          className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          {taxLoading ? (
            <span className="animate-pulse">Generating report…</span>
          ) : (
            <>
              <span>⬇</span>
              <span>Download Tax Report  (FY 2025-26)</span>
            </>
          )}
        </button>
        {taxError && <p className="text-xs text-red-500 mt-1.5">{taxError}</p>}
        <p className="text-xs text-gray-400 mt-1.5">
          Excel with STCG / LTCG, F&amp;O P&amp;L, per-stock realized gains &amp; open positions
        </p>
      </div>
    </div>
  );
}

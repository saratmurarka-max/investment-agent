import { useEffect, useRef, useState } from "react";
import { type StockResult, addHolding, downloadTaxReport, searchStocks, uploadHoldingsExcel } from "../api/client";

interface Props {
  portfolioId: number;
  onAdded: () => void;
}

type Tab = "manual" | "excel";

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

  // Fetch suggestions whenever the debounced input changes
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

  // Close dropdown on outside click
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
  const [taxError,   setTaxError]   = useState<string | null>(null);

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

  // --- Excel upload ---
  const [dragOver, setDragOver] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<{
    added: number; tickers: string[]; skipped: string[];
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
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

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 className="font-semibold text-gray-800 mb-4">Add Holdings</h2>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-gray-100 rounded-lg p-1">
        {(["manual", "excel"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
              tab === t ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "manual" ? "Manual Entry" : "Upload Excel"}
          </button>
        ))}
      </div>

      {/* ── Manual Entry ── */}
      {tab === "manual" && (
        <form onSubmit={handleManualSubmit} className="space-y-3">

          {/* Ticker autocomplete */}
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

            {/* Dropdown */}
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

            {/* Confirmation badge */}
            {selectedStock && (
              <p className="text-xs text-green-600 mt-1">
                Ticker: <span className="font-mono font-medium">{selectedStock.ticker}</span>
              </p>
            )}
          </div>

          {/* Shares & Avg Cost */}
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

      {/* ── Excel Upload ── */}
      {tab === "excel" && (
        <div className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault(); setDragOver(false);
              const f = e.dataTransfer.files[0];
              if (f) handleFile(f);
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
              {uploadLoading ? "Uploading..." : "Drop your Excel file here"}
            </p>
            <p className="text-xs text-gray-400 mt-1">or click to browse — .xlsx only</p>
            <input
              ref={fileInputRef} type="file" accept=".xlsx" className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </div>

          {/* Format hint */}
          <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-500">
            <p className="font-medium text-gray-600 mb-1">Expected columns (row 1 = headers):</p>
            <table className="w-full text-center">
              <thead>
                <tr className="text-gray-400">
                  <th className="font-medium pb-1">Ticker</th>
                  <th className="font-medium pb-1">Shares</th>
                  <th className="font-medium pb-1">Avg Cost</th>
                </tr>
              </thead>
              <tbody>
                <tr><td className="font-mono">RELIANCE.NS</td><td>10</td><td>2500.00</td></tr>
                <tr><td className="font-mono">INFY.NS</td><td>5</td><td>1800.00</td></tr>
              </tbody>
            </table>
            <p className="mt-2 text-gray-400">
              Use <span className="font-mono">.NS</span> suffix for NSE stocks.
            </p>
          </div>

          {uploadError && <p className="text-xs text-red-500">{uploadError}</p>}

          {uploadResult && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
              <p className="font-medium">Import complete</p>
              <p>
                {uploadResult.added} stock{uploadResult.added !== 1 ? "s" : ""} added:{" "}
                {uploadResult.tickers.join(", ")}
              </p>
              {uploadResult.skipped.length > 0 && (
                <p className="text-yellow-600 mt-1">Skipped: {uploadResult.skipped.join(", ")}</p>
              )}
            </div>
          )}
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
          Excel with STCG / LTCG summary, per-stock realized gains &amp; open positions
        </p>
      </div>
    </div>
  );
}

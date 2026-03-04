import { useRef, useState } from "react";
import {
  clearAllHoldings,
  clearDerivatives,
  downloadTaxReport,
  uploadDerivativesExcel,
  uploadHoldingsExcel,
} from "../api/client";

interface Props {
  portfolioId: number;
  onAdded: () => void;
}

type Tab = "excel" | "derivatives" | "clear";

const TAB_LABELS: Record<Tab, string> = {
  excel:       "Upload Equity File",
  derivatives: "Upload Derivatives File",
  clear:       "Clear All",
};

export default function AddHoldings({ portfolioId, onAdded }: Props) {
  const [tab, setTab] = useState<Tab>("excel");

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
  const derivFileRef = useRef<HTMLInputElement>(null);

  async function handleDerivFile(file: File) {
    setDerivError(null);
    setDerivResult(null);
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

  // --- Clear all (equity + derivatives) ---
  const [clearLoading, setClearLoading] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);
  const [clearMsg, setClearMsg] = useState<string | null>(null);

  async function handleClearAll() {
    if (!confirm(
      "Delete ALL equity holdings, realized P&L, and derivative trades from this portfolio?\n\n" +
      "This cannot be undone. You can re-upload your broker files afterwards."
    )) return;
    setClearLoading(true);
    setClearError(null);
    setClearMsg(null);
    try {
      const [equityResult, derivResult] = await Promise.all([
        clearAllHoldings(portfolioId),
        clearDerivatives(portfolioId),
      ]);
      const parts: string[] = [];
      if (equityResult.deleted_holdings > 0) {
        parts.push(`${equityResult.deleted_holdings} holding${equityResult.deleted_holdings !== 1 ? "s" : ""}`);
      }
      if (derivResult.deleted > 0) {
        parts.push(`${derivResult.deleted} derivative trade${derivResult.deleted !== 1 ? "s" : ""}`);
      }
      setClearMsg(parts.length > 0 ? `Cleared: ${parts.join(" and ")}.` : "Nothing to clear.");
      onAdded();
    } catch (err: unknown) {
      setClearError(err instanceof Error ? err.message : "Failed to clear data.");
    } finally {
      setClearLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 className="font-semibold text-gray-800 mb-4">Add Holdings</h2>

      {/* Tabs — 3 tabs in a row */}
      <div className="grid grid-cols-3 gap-1 mb-5 bg-gray-100 rounded-lg p-1">
        {(["excel", "derivatives", "clear"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`py-1.5 text-xs font-medium rounded-md transition-colors ${
              tab === t ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
            } ${t === "clear" ? (tab === t ? "text-red-600" : "text-red-500 hover:text-red-700") : ""}`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

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

          {derivResult && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
              <p className="font-medium">Import complete</p>
              <p>{derivResult.imported} derivative trade{derivResult.imported !== 1 ? "s" : ""} imported.</p>
              {derivResult.skipped.length > 0 && (
                <p className="text-yellow-600 mt-1">Skipped: {derivResult.skipped.join(", ")}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Clear All ── */}
      {tab === "clear" && (
        <div className="space-y-4">
          <div className="bg-red-50 border border-red-200 rounded-xl p-5 text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <p className="text-sm font-semibold text-red-700 mb-1">Clear All Portfolio Data</p>
            <p className="text-xs text-red-600">
              This will permanently delete all equity holdings, realized P&amp;L, and derivative
              trades from this portfolio. This action cannot be undone.
            </p>
          </div>

          <p className="text-xs text-gray-500 text-center">
            After clearing, you can upload new broker files.
          </p>

          {clearError && <p className="text-xs text-red-500 text-center">{clearError}</p>}
          {clearMsg && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700 text-center">
              <p className="font-medium">{clearMsg}</p>
              <p className="mt-0.5">You can now upload new files.</p>
            </div>
          )}

          <button
            onClick={handleClearAll}
            disabled={clearLoading}
            className="w-full bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            {clearLoading ? "Clearing..." : "Delete All Holdings & Trades"}
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

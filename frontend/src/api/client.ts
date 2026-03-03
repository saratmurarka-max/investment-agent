const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export async function streamChat(
  messages: Message[],
  portfolioId: number | null,
  onChunk: (chunk: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE_URL}/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, portfolio_id: portfolioId }),
    signal,
  });

  if (!res.ok) throw new Error(`Chat error: ${res.status}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

export async function getPortfolio(portfolioId: number) {
  const res = await fetch(`${BASE_URL}/portfolios/${portfolioId}`);
  if (!res.ok) throw new Error("Failed to load portfolio");
  return res.json();
}

export async function getClientPortfolios(clientId: number) {
  const res = await fetch(`${BASE_URL}/portfolios/clients/${clientId}/portfolios`);
  if (!res.ok) throw new Error("Failed to load portfolios");
  return res.json();
}

export interface StockResult {
  symbol: string;
  ticker: string; // e.g. RELIANCE.NS
  name: string;
}

export async function searchStocks(query: string, limit = 10): Promise<StockResult[]> {
  if (!query.trim()) return [];
  const res = await fetch(
    `${BASE_URL}/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  if (!res.ok) return [];
  return res.json();
}

export async function addHolding(
  portfolioId: number,
  holding: { ticker: string; shares: number; avg_cost: number }
) {
  const res = await fetch(`${BASE_URL}/portfolios/${portfolioId}/holdings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(holding),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to add holding");
  }
  return res.json();
}

export async function uploadHoldingsExcel(portfolioId: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/portfolios/${portfolioId}/holdings/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

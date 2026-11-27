export type Candidate = {
  symbol: string;
  candidate_status: string;
  latest_price: string | number | null;
  trend_conditions_passed: string | number | null;
  relative_strength: string | number | null;
  breakout_status: string;
  rejection_reasons: string;
  entry_reference?: string | number | null; stop_loss?: string | number | null;
  target_price?: string | number | null; planned_quantity?: string | number | null;
  confidence_pct?: string | number | null; eligible_for_paper?: string | boolean;
};

export type Position = {
  id: number;
  symbol: string;
  quantity: number;
  entry_price: number;
  stop_loss: number;
  target_price: number | null;
  opened_on: string;
  status: string;
  mark_price: number | null;
  unrealized_pnl: number | null;
  manual_record_only: boolean;
};

export type Dashboard = {
  freshness: {
    status: string;
    expected_session: string;
    latest_data_date: string | null;
    message: string;
    candidates: Candidate[];
  };
  risk_config: {
    total_capital: number;
    max_deployment: number;
    max_risk_per_trade: number;
    max_open_positions: number;
    max_position_value: number;
    holding_sessions: number[];
  };
  watchlist: { symbol: string; added_at: string }[];
  portfolio: Position[];
  database_available: boolean;
  local_only: boolean;
  orders_enabled: boolean;
  telegram_configured: boolean;
};

export type PaperTrade = {
  id: number; symbol: string; quantity: number; entry_price: number;
  stop_loss: number; target_price: number | null; opened_on: string;
  status: 'OPEN' | 'CLOSED'; exit_price: number | null; closed_on: string | null;
  realized_pnl_before_costs: number | null;
};

export type ForwardTrade = {
  id: number; symbol: string; signal_date: string; signal_rank: number; confidence_pct: number;
  reference_close: number; stop_loss: number; target_price: number; status: string;
  quantity: number; entry_date: string | null; entry_price: number | null;
  exit_date: string | null; exit_price: number | null; exit_reason: string | null;
  fees: number; net_pnl: number | null; mark_price: number | null; unrealized_pnl: number | null; holding_sessions: number;
};
export type ForwardBook = {
  summary: { sessions_processed: number; queued_trades: number; open_trades: number;
    closed_trades: number; win_rate_percent: number | null; profit_factor: number | string | null; average_win_loss_ratio: number | null;
    max_drawdown_percent: number; net_realized_pnl: number; unrealized_pnl: number; costs_included: boolean; slippage_bps_per_side: number;
    brokerage_assumption: string; live_orders_placed: false; mode: string };
  trades: ForwardTrade[]; sessions: { session_date: string; queued: number; opened: number; closed: number }[];
  latest_session: string | null; eligible_setups: { id: number; symbol: string; signal_date: string;
    reference_close: number; stop_loss: number; target_price: number; planned_quantity: number;
    confidence_pct: number; relative_strength: number; status: string }[];
};

export type HistoricalReplay = {
  available: boolean;
  metrics: Record<string, unknown> | null;
  assumptions: Record<string, string>;
  trades: Record<string, string>[];
  equity_curve: Record<string, string>[];
  live_orders_placed?: false;
};

export type PaperTradeBook = {
  summary: {
    closed_trades: number; open_trades: number;
    realized_pnl_before_costs: number; win_rate_percent: number | null;
    profit_factor: number | string | null; costs_included: false;
    live_orders_placed: false;
  };
  trades: PaperTrade[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<Dashboard>('/api/dashboard'),
  addWatchlist: (symbol: string) => request('/api/watchlist', {
    method: 'POST', body: JSON.stringify({ symbol }),
  }),
  removeWatchlist: (symbol: string) => request(`/api/watchlist/${encodeURIComponent(symbol)}`, {
    method: 'DELETE',
  }),
  addPosition: (data: object) => request('/api/portfolio', {
    method: 'POST', body: JSON.stringify(data),
  }),
  closePosition: (id: number, exitPrice: number) => request(`/api/portfolio/${id}/close`, {
    method: 'POST', body: JSON.stringify({
      exit_price: exitPrice, closed_on: localDate(), manual_confirmation: true,
    }),
  }),
  paperTrades: () => request<PaperTradeBook>('/api/paper-trades'),
  forwardPaper: () => request<ForwardBook>('/api/forward-paper'),
  historicalBacktest: () => request<HistoricalReplay>('/api/backtest'),
  setForwardPaperMode: (mode: string) => request<{mode: string}>('/api/forward-paper/mode', { method: 'PUT', body: JSON.stringify({mode}) }),
  approveForwardTrade: (id: number) => request(`/api/forward-paper/${id}/approve`, { method: 'POST', body: JSON.stringify({manual_confirmation: true}) }),
  addPaperTrade: (data: object) => request('/api/paper-trades', {
    method: 'POST', body: JSON.stringify(data),
  }),
  closePaperTrade: (id: number, exitPrice: number) => request(`/api/paper-trades/${id}/close`, {
    method: 'POST', body: JSON.stringify({
      exit_price: exitPrice, closed_on: localDate(), simulation_confirmation: true,
    }),
  }),
  sendTelegramAlert: () => request('/api/alerts/telegram', {
    method: 'POST', body: JSON.stringify({ manual_confirmation: true }),
  }),
};

export function localDate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

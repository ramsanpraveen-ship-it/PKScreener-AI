import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CircularProgress,
  Container, Divider, IconButton, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Toolbar, Typography,
} from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import RefreshIcon from '@mui/icons-material/Refresh';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import { api, clearApiToken, localDate, setApiToken, type Dashboard } from './api';
import ForwardTrading from './ForwardTrading';
import HistoricalReplay from './HistoricalReplay';
import StrategyIntelligence from './StrategyIntelligence';

const money = (value: number | string | null | undefined) => {
  const number = Number(value);
  return Number.isFinite(number) ? `₹${number.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
};

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <Card><CardContent>
    <Typography color="text.secondary" variant="body2">{label}</Typography>
    <Typography variant="h5" sx={{ mt: 1, fontWeight: 700 }}>{value}</Typography>
    {sub && <Typography color="text.secondary" variant="caption">{sub}</Typography>}
  </CardContent></Card>;
}

export default function App() {
  const [apiToken, setApiTokenState] = useState(() => sessionStorage.getItem('pkscreener.localApiToken') || '');
  const [tokenInput, setTokenInput] = useState('');
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [symbol, setSymbol] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [positionForm, setPositionForm] = useState(false);
  const [form, setForm] = useState({ symbol: '', quantity: '', entry_price: '', stop_loss: '', target_price: '', opened_on: localDate() });
  const [manualConfirmed, setManualConfirmed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const next = await api.dashboard();
      setData(next);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The local API is unavailable.');
    } finally {
      setLoading(false);
    }
  }, [apiToken]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const perform = async (work: () => Promise<unknown>, success: string) => {
    try {
      await work();
      setActionMessage(success);
      await refresh();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : 'Action failed.');
    }
  };

  const addWatchlist = (event: FormEvent) => {
    event.preventDefault();
    if (!symbol.trim()) return;
    void perform(() => api.addWatchlist(symbol.trim().toUpperCase()), `${symbol.trim().toUpperCase()} added to watchlist.`);
    setSymbol('');
  };

  const addPosition = (event: FormEvent) => {
    event.preventDefault();
    if (!manualConfirmed) {
      setActionMessage('Confirm that this is a manually recorded position. No order will be placed.');
      return;
    }
    const payload = {
      symbol: form.symbol.toUpperCase(),
      quantity: Number(form.quantity),
      entry_price: Number(form.entry_price),
      stop_loss: Number(form.stop_loss),
      target_price: form.target_price ? Number(form.target_price) : null,
      opened_on: form.opened_on,
      manual_recorded: true,
    };
    void perform(() => api.addPosition(payload), 'Position recorded locally. No order was placed.');
    setPositionForm(false);
    setManualConfirmed(false);
  };

  const submitToken = (event: FormEvent) => {
    event.preventDefault();
    if (!tokenInput.trim()) return;
    setApiToken(tokenInput.trim());
    setApiTokenState(tokenInput.trim());
    setTokenInput('');
    setLoading(true);
  };

  const freshness = data?.freshness;
  const isFresh = freshness?.status === 'FRESH';

  return <Box sx={{ minHeight: '100vh', pb: 6 }}>
    <AppBar position="static" color="transparent" elevation={0}>
      <Toolbar sx={{ maxWidth: 1440, width: '100%', mx: 'auto', px: { xs: 2, md: 4 } }}>
        <ShowChartIcon color="primary" sx={{ mr: 1.5 }} />
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h6" fontWeight={800}>PKScreener AI</Typography>
          <Typography variant="caption" color="text.secondary">NSE cash-equity research terminal</Typography>
        </Box>
        <Chip size="small" color="success" variant="outlined" label="LOCAL ONLY" />
        {apiToken && <Button size="small" onClick={() => { clearApiToken(); setApiTokenState(''); setData(null); }}>Sign out</Button>}
        <IconButton onClick={() => void refresh()} aria-label="Refresh dashboard" sx={{ ml: 1 }}><RefreshIcon /></IconButton>
      </Toolbar>
    </AppBar>

    <Container maxWidth="xl" sx={{ mt: 3 }}>
      {!apiToken && <Card sx={{ maxWidth: 520, mx: 'auto', mt: 8 }}><CardContent>
        <Typography variant="h5" fontWeight={700} gutterBottom>Local API sign in</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Enter the token configured in your local API environment. It stays in this browser tab session and is never sent to a remote server.</Typography>
        <Box component="form" onSubmit={submitToken}>
          <Stack spacing={2}><TextField label="Local API token" type="password" autoComplete="current-password" value={tokenInput} onChange={event => setTokenInput(event.target.value)} required />
            <Button type="submit" variant="contained">Connect</Button></Stack>
        </Box>
        {error && <Alert severity="warning" sx={{ mt: 2 }}>{error}</Alert>}
      </CardContent></Card>}
      {apiToken && <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error} Start the local API to load the dashboard.</Alert>}
      {actionMessage && <Alert severity={/failed|Confirm|require|available|rejected|limit|not configured|unavailable|exceed/i.test(actionMessage) ? 'warning' : 'success'} onClose={() => setActionMessage('')} sx={{ mb: 2 }}>{actionMessage}</Alert>}
      {loading && !data ? <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 320 }}><CircularProgress /></Box> : data && <>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={2} sx={{ mb: 2 }}>
          <Box>
            <Typography variant="h4" fontWeight={800}>Research overview</Typography>
            <Typography color="text.secondary">Python controls screening and risk. Local AI provides explanations only.</Typography>
          </Box>
          <Chip color={isFresh ? 'success' : 'warning'} label={isFresh ? `FRESH · ${freshness?.expected_session}` : `DATA GATE · ${freshness?.status ?? 'UNKNOWN'}`} />
        </Stack>

        {!isFresh && <Alert severity="warning" sx={{ mb: 3 }}>
          {freshness?.message ?? 'No validated scan is available.'} Candidate rows are hidden until every stock and the benchmark match the expected NSE session.
          {freshness?.latest_data_date && <> Latest scan data: {freshness.latest_data_date}. Expected: {freshness.expected_session}.</>}
        </Alert>}
        {!data.database_available && <Alert severity="info" sx={{ mb: 3 }}>
          Local PostgreSQL is not connected. Scanner status remains available; watchlist and portfolio edits are disabled until the database is ready.
        </Alert>}

        <Box className="metric-grid">
          <Metric label="Total capital" value={money(data.risk_config.total_capital)} />
          <Metric label="Deployment limit" value={money(data.risk_config.max_deployment)} />
          <Metric label="Risk per trade" value={money(data.risk_config.max_risk_per_trade)} />
          <Metric label="Manual positions" value={`${data.portfolio.filter(p => p.status === 'OPEN').length} / ${data.risk_config.max_open_positions}`} />
        </Box>

        <ForwardTrading fresh={isFresh} expectedSession={freshness?.expected_session ?? null} />
        <HistoricalReplay />
        <StrategyIntelligence />


        <Box className="lower-grid" sx={{ mt: 3 }}>
          <Card><CardContent>
            <Typography variant="h6" fontWeight={700}>Watchlist</Typography>
            <Box component="form" onSubmit={addWatchlist} sx={{ display: 'flex', gap: 1, mt: 2 }}>
              <TextField size="small" label="NSE symbol" value={symbol} onChange={e => setSymbol(e.target.value)} fullWidth disabled={!data.database_available} />
              <Button type="submit" variant="contained" disabled={!data.database_available || !symbol.trim()}>Add</Button>
            </Box>
            <Stack spacing={0.5} sx={{ mt: 2 }}>
              {!data.watchlist.length && <Typography variant="body2" color="text.secondary">Your saved symbols will appear here.</Typography>}
              {data.watchlist.map(item => <Stack key={item.symbol} direction="row" alignItems="center" justifyContent="space-between">
                <Typography fontWeight={600}>{item.symbol}</Typography>
                <IconButton size="small" disabled={!data.database_available} onClick={() => void perform(() => api.removeWatchlist(item.symbol), `${item.symbol} removed.`)} aria-label={`Remove ${item.symbol}`}><DeleteOutlineIcon fontSize="small" /></IconButton>
              </Stack>)}
            </Stack>
          </CardContent></Card>

          <Card><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Box><Typography variant="h6" fontWeight={700}>Portfolio tracker</Typography><Typography variant="body2" color="text.secondary">Manual records only</Typography></Box>
              <Button size="small" onClick={() => setPositionForm(v => !v)} disabled={!data.database_available}>Record position</Button>
            </Stack>
            {positionForm && <Box component="form" onSubmit={addPosition} className="position-form">
              {([['symbol', 'Symbol'], ['quantity', 'Quantity'], ['entry_price', 'Entry price'], ['stop_loss', 'Stop loss'], ['target_price', 'Target reference'], ['opened_on', 'Opened on']] as const).map(([key, label]) => <TextField key={key} size="small" label={label} type={key === 'opened_on' ? 'date' : key === 'symbol' ? 'text' : 'number'} InputLabelProps={key === 'opened_on' ? { shrink: true } : undefined} value={form[key]} onChange={e => setForm(old => ({ ...old, [key]: e.target.value }))} required={key !== 'target_price'} />)}
              <label className="confirm-label"><input type="checkbox" checked={manualConfirmed} onChange={e => setManualConfirmed(e.target.checked)} /> I entered this position manually. No order will be placed.</label>
              <Button type="submit" variant="contained" disabled={!manualConfirmed}>Save record</Button>
            </Box>}
            <Divider sx={{ my: 1.5 }} />
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small"><TableHead><TableRow><TableCell>Symbol</TableCell><TableCell>Qty</TableCell><TableCell>Entry</TableCell><TableCell>Mark</TableCell><TableCell>P&amp;L</TableCell><TableCell>Status</TableCell><TableCell /></TableRow></TableHead>
                <TableBody>
                  {data.portfolio.map(position => <TableRow key={position.id}>
                    <TableCell>{position.symbol}</TableCell><TableCell>{position.quantity}</TableCell><TableCell>{money(position.entry_price)}</TableCell><TableCell>{money(position.mark_price)}</TableCell><TableCell>{money(position.unrealized_pnl)}</TableCell><TableCell>{position.status}</TableCell>
                    <TableCell>{position.status === 'OPEN' && position.mark_price !== null && <Button size="small" onClick={() => window.confirm(`Record ${position.symbol} as manually closed at ${money(position.mark_price)}? No order will be placed.`) && void perform(() => api.closePosition(position.id, position.mark_price!), `${position.symbol} close recorded.`)}>Close record</Button>}</TableCell>
                  </TableRow>)}
                  {!data.portfolio.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>No manually recorded positions.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Box>
          </CardContent></Card>
        </Box>


        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 3 }}>
          <Chip variant="outlined" label={`Position cap ${money(data.risk_config.max_position_value)}`} />
          <Chip variant="outlined" label={`Holding guide ${data.risk_config.holding_sessions[0]}–${data.risk_config.holding_sessions[1]} sessions`} />
          <Chip variant="outlined" color="warning" label="Paper modes only · Kite orders disabled" />
          <Button variant="outlined" disabled={!data.telegram_configured} onClick={() => window.confirm('Send today’s fresh research candidates to your configured Telegram chat?') && void perform(() => api.sendTelegramAlert(), 'Fresh candidate alert sent to Telegram.')}>Send Telegram alert</Button>
          {!data.telegram_configured && <Chip variant="outlined" label="Telegram off · configure locally to enable" />}
        </Stack>
      </>}
      </>}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 4 }}>
        Paper simulation only. Daily trade state advances only after the local freshness gate validates every stock and benchmark session; Kite orders are disabled.
      </Typography>
    </Container>
  </Box>;
}

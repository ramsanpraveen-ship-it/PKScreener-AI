import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Chip, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { api, localDate, type PaperTradeBook } from './api';

const initial = { symbol: '', quantity: '', entry_price: '', stop_loss: '', target_price: '', opened_on: localDate() };
const money = (value: number | null | undefined) => value == null ? '—' : `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

export default function PaperTrading({ enabled, onChange }: { enabled: boolean; onChange: () => void }) {
  const [book, setBook] = useState<PaperTradeBook | null>(null);
  const [form, setForm] = useState(initial);
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try { setBook(await api.paperTrades()); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load the paper journal.'); }
  }, [enabled]);
  useEffect(() => { void refresh(); }, [refresh]);

  const addTrade = async (event: FormEvent) => {
    event.preventDefault();
    if (!confirmed) return;
    try {
      await api.addPaperTrade({
        symbol: form.symbol.toUpperCase(), quantity: Number(form.quantity),
        entry_price: Number(form.entry_price), stop_loss: Number(form.stop_loss),
        target_price: form.target_price ? Number(form.target_price) : null,
        opened_on: form.opened_on, simulation_confirmation: true,
      });
      setForm(initial); setConfirmed(false); setMessage('Simulated trade recorded. No order was sent.');
      await refresh(); onChange();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Paper trade was rejected.'); }
  };

  const closeTrade = async (id: number, symbol: string) => {
    const raw = window.prompt(`Enter the simulated exit price for ${symbol}. No order will be sent.`);
    if (!raw) return;
    const price = Number(raw);
    if (!Number.isFinite(price) || price <= 0) { setMessage('Enter a positive exit price.'); return; }
    try {
      await api.closePaperTrade(id, price); setMessage(`${symbol} paper trade closed.`);
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not close paper trade.'); }
  };

  return <Card sx={{ mt: 3 }}><CardContent>
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1}>
      <Box><Typography variant="h6" fontWeight={700}>Paper trading journal</Typography>
        <Typography variant="body2" color="text.secondary">Manual simulations only · historical results exclude costs</Typography></Box>
      <Chip size="small" color="warning" variant="outlined" label="NO LIVE ORDERS" />
    </Stack>
    {message && <Alert severity={message.includes('recorded') || message.includes('closed') ? 'success' : 'warning'} onClose={() => setMessage('')} sx={{ mt: 1 }}>{message}</Alert>}
    {enabled && book && <Stack direction="row" spacing={1} sx={{ my: 2, flexWrap: 'wrap' }}>
      <Chip label={`Closed ${book.summary.closed_trades}`} />
      <Chip label={`Open ${book.summary.open_trades}`} />
      <Chip label={`Realized P&L ${money(book.summary.realized_pnl_before_costs)}`} />
      <Chip label={`Win rate ${book.summary.win_rate_percent == null ? '—' : `${book.summary.win_rate_percent.toFixed(1)}%`}`} />
      <Chip label={`Profit factor ${book.summary.profit_factor ?? '—'}`} />
    </Stack>}
    {!enabled && <Alert severity="info" sx={{ mt: 2 }}>Connect the local database to save simulated trades.</Alert>}
    <Box component="form" onSubmit={addTrade} className="position-form" sx={{ my: 2 }}>
      {([['symbol', 'Symbol'], ['quantity', 'Quantity'], ['entry_price', 'Simulated entry'], ['stop_loss', 'Stop loss'], ['target_price', 'Target reference'], ['opened_on', 'Opened on']] as const).map(([key, label]) =>
        <TextField key={key} size="small" label={label} type={key === 'opened_on' ? 'date' : key === 'symbol' ? 'text' : 'number'} InputLabelProps={key === 'opened_on' ? { shrink: true } : undefined} value={form[key]} onChange={event => setForm(old => ({ ...old, [key]: event.target.value }))} required={key !== 'target_price'} disabled={!enabled} />)}
      <label className="confirm-label"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={!enabled} /> I confirm this is simulated paper trading; no broker order will be sent.</label>
      <Button type="submit" variant="contained" disabled={!enabled || !confirmed}>Record simulation</Button>
    </Box>
    <Box sx={{ overflowX: 'auto' }}><Table size="small"><TableHead><TableRow><TableCell>Symbol</TableCell><TableCell>Qty</TableCell><TableCell>Entry</TableCell><TableCell>Exit</TableCell><TableCell>Realized P&amp;L</TableCell><TableCell>Status</TableCell><TableCell /></TableRow></TableHead>
      <TableBody>{(book?.trades ?? []).map(trade => <TableRow key={trade.id}>
        <TableCell>{trade.symbol}</TableCell><TableCell>{trade.quantity}</TableCell><TableCell>{money(trade.entry_price)}</TableCell><TableCell>{money(trade.exit_price)}</TableCell><TableCell>{money(trade.realized_pnl_before_costs)}</TableCell><TableCell>{trade.status}</TableCell>
        <TableCell>{trade.status === 'OPEN' && <Button size="small" disabled={!enabled} onClick={() => void closeTrade(trade.id, trade.symbol)}>Close simulation</Button>}</TableCell>
      </TableRow>)}{book && !book.trades.length && <TableRow><TableCell colSpan={7} align="center">No simulated trades recorded.</TableCell></TableRow>}</TableBody></Table></Box>
  </CardContent></Card>;
}

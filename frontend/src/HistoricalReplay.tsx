import { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Card, CardContent, CircularProgress, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { api, type HistoricalReplay as Replay } from './api';

const money = (value: unknown) => {
  const number = Number(value);
  return Number.isFinite(number) ? `₹${number.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
};
const pct = (value: unknown) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : '—';

export default function HistoricalReplay() {
  const [report, setReport] = useState<Replay | null>(null);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    try { setReport(await api.historicalBacktest()); setError(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Historical replay is unavailable.'); }
  }, []);
  useEffect(() => { void reload(); const timer = window.setInterval(() => void reload(), 60_000); return () => window.clearInterval(timer); }, [reload]);

  const m = report?.metrics;
  const value = (key: string) => m?.[key];
  const interval = value('win_rate_95ci_pct');
  const intervalText = Array.isArray(interval) ? `${Number(interval[0]).toFixed(1)}%–${Number(interval[1]).toFixed(1)}%` : 'not available';
  const curve = (report?.equity_curve ?? []).map(row => ({
    equity: Number(row.equity),
    benchmark: Number(row.benchmark_equity),
  })).filter(row => Number.isFinite(row.equity) && Number.isFinite(row.benchmark));
  const chartMin = Math.min(...curve.flatMap(point => [point.equity, point.benchmark]));
  const chartMax = Math.max(...curve.flatMap(point => [point.equity, point.benchmark]));
  let peak = Number.NEGATIVE_INFINITY;
  const drawdowns = curve.map(point => { peak = Math.max(peak, point.equity); return (point.equity / peak - 1) * 100; });
  const linePath = (values: number[]) => {
    if (values.length < 2) return '';
    const span = chartMax - chartMin || 1;
    return values.map((v, i) => `${i ? 'L' : 'M'} ${(i / (values.length - 1) * 600).toFixed(1)} ${(95 - (v - chartMin) / span * 85).toFixed(1)}`).join(' ');
  };
  const drawdownPath = () => {
    if (drawdowns.length < 2) return '';
    const low = Math.min(...drawdowns), span = Math.abs(low) || 1;
    return drawdowns.map((v, i) => `${i ? 'L' : 'M'} ${(i / (drawdowns.length - 1) * 600).toFixed(1)} ${(10 + (v - low) / span * 85).toFixed(1)}`).join(' ');
  };
  const walkForward = value('walk_forward') as { method?: string; periods?: Record<string, { start_date: string; end_date: string; metrics: Record<string, unknown> }> } | undefined;
  const monthly = value('monthly_returns_pct') as Record<string, number> | undefined;
  const metrics = [
    ['Net result', money(value('final_equity') == null ? null : Number(value('final_equity')) - Number(value('initial_equity')))],
    ['Win rate', pct(value('win_rate_pct'))],
    ['Profit factor', value('profit_factor') == null ? '—' : String(value('profit_factor'))],
    ['Avg win / loss', value('average_win_loss_ratio') == null ? '—' : String(value('average_win_loss_ratio'))],
    ['Maximum drawdown', pct(value('max_drawdown_pct'))],
    ['Trades', String(value('trade_count') ?? 0)],
  ];

  return <Card sx={{ mt: 3 }}><CardContent>
    <Typography variant="h6" fontWeight={700}>Historical paper replay</Typography>
    <Typography variant="body2" color="text.secondary">{String(value('start_date') ?? 'No replay yet')} to {String(value('end_date') ?? '')} · rule based, next-session fills · no broker orders</Typography>
    {error && <Alert severity="warning" sx={{ mt: 1 }}>{error}</Alert>}
    {!report && !error && <CircularProgress size={22} sx={{ mt: 2 }} />}
    {report && !report.available && <Alert severity="info" sx={{ mt: 1 }}>Run the historical replay to populate this report.</Alert>}
    {report?.available && <>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(6, 1fr)' }, gap: 1, mt: 2 }}>
        {metrics.map(([label, val]) => <Card variant="outlined" key={label}><CardContent sx={{ p: '12px !important' }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography fontWeight={700}>{val}</Typography></CardContent></Card>)}
      </Box>
      <Alert severity="warning" sx={{ mt: 2 }}>
        This is historical research, not a forecast. {String(value('trade_count') ?? 0)} trades; the 95% Wilson interval for win rate is {intervalText}. The strategy returned {pct(value('total_return_pct'))} versus Nifty 50 TRI {pct(value('nifty50_tri_return_pct'))}. Treat short samples as exploratory.
      </Alert>
      {curve.length > 1 && <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2">Portfolio equity and Nifty 50 TRI (₹100,000 start)</Typography>
        <Box component="svg" viewBox="0 0 600 110" role="img" aria-label="Equity curve versus Nifty 50 TRI" sx={{ width: '100%', height: 180, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
          <path d={linePath(curve.map(point => point.equity))} fill="none" stroke="#1976d2" strokeWidth="2" />
          <path d={linePath(curve.map(point => point.benchmark))} fill="none" stroke="#ed6c02" strokeWidth="2" />
        </Box>
        <Typography variant="caption" color="text.secondary">Blue: strategy equity · orange: Nifty 50 TRI · monthly marks are in the report data.</Typography>
        <Typography variant="subtitle2" sx={{ mt: 1 }}>Drawdown</Typography>
        <Box component="svg" viewBox="0 0 600 110" role="img" aria-label="Portfolio drawdown chart" sx={{ width: '100%', height: 130, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
          <path d={drawdownPath()} fill="none" stroke="#d32f2f" strokeWidth="2" />
        </Box>
      </Box>}
      {walkForward?.periods && <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2" fontWeight={700}>Walk-forward results</Typography>
        <Typography variant="caption" color="text.secondary">{walkForward.method}</Typography>
        <Table size="small"><TableHead><TableRow>{['Period', 'Dates', 'Net return', 'Nifty 50 TRI', 'Trades', 'Max drawdown'].map(x => <TableCell key={x}>{x}</TableCell>)}</TableRow></TableHead>
          <TableBody>{Object.entries(walkForward.periods).map(([name, period]) => <TableRow key={name} sx={name === 'out_of_sample' ? { bgcolor: 'action.selected' } : undefined}>
            <TableCell>{name === 'out_of_sample' ? 'Out of sample' : name[0].toUpperCase() + name.slice(1)}</TableCell><TableCell>{period.start_date} – {period.end_date}</TableCell>
            <TableCell>{pct(period.metrics.total_return_pct)}</TableCell><TableCell>{pct(period.metrics.nifty50_tri_return_pct)}</TableCell><TableCell>{String(period.metrics.trade_count ?? 0)}</TableCell><TableCell>{pct(period.metrics.max_drawdown_pct)}</TableCell>
          </TableRow>)}</TableBody>
        </Table>
      </Box>}
      {monthly && Object.keys(monthly).length > 0 && <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2">Monthly returns on total portfolio capital</Typography>
        <Table size="small"><TableHead><TableRow><TableCell>Month</TableCell><TableCell align="right">Return</TableCell></TableRow></TableHead><TableBody>
          {Object.entries(monthly).map(([month, result]) => <TableRow key={month}><TableCell>{month}</TableCell><TableCell align="right">{pct(result)}</TableCell></TableRow>)}
        </TableBody></Table>
      </Box>}
      <Box sx={{ overflowX: 'auto', mt: 2 }}><Table size="small"><TableHead><TableRow>
        {['Symbol', 'Signal', 'Entry', 'Exit', 'Qty', 'Stop', 'Target', 'Exit rule', 'Net P&L'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>
        {report.trades.map((trade, index) => <TableRow key={`${trade.symbol}-${trade.entry_date}-${index}`}>
          <TableCell>{trade.symbol}</TableCell><TableCell>{trade.signal_date}</TableCell>
          <TableCell>{trade.entry_date} / {money(trade.entry_fill)}</TableCell><TableCell>{trade.exit_date} / {money(trade.exit_fill)}</TableCell>
          <TableCell>{trade.quantity}</TableCell><TableCell>{money(trade.stop_loss)}</TableCell><TableCell>{money(trade.target)}</TableCell>
          <TableCell>{trade.exit_reason}</TableCell><TableCell>{money(trade.net_pnl)}</TableCell>
        </TableRow>)}
        {!report.trades.length && <TableRow><TableCell colSpan={9} align="center">No historical trades were generated.</TableCell></TableRow>}
      </TableBody></Table></Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>Costs, estimated slippage, risk limits, point-in-time membership and benchmark details are recorded in the local replay assumptions file. Dividends are included where sourced. Historical replay remains separate from forward paper-trading statistics.</Typography>
    </>}
  </CardContent></Card>;
}

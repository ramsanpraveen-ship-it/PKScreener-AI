import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Card, CardContent, Chip, CircularProgress, Table,
  TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import { api, type StrategyIntelligenceReport } from './api';

const number = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);

export default function StrategyIntelligence() {
  const [report, setReport] = useState<StrategyIntelligenceReport | null>(null);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    try { setReport(await api.strategyIntelligence()); setError(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Strategy diagnostics are unavailable.'); }
  }, []);
  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => void reload(), 60_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const summary = report?.diagnostic_summary;
  const metrics = report?.baseline_metrics;
  const tagLabels: Record<string, string> = {
    TIME_EXIT_NET_LOSS: 'Time exit loss',
    MFE_BELOW_1R: 'MFE below 1R',
    MAE_AT_LEAST_MINUS_0_5R: 'MAE ≤ −0.5R',
    BEARISH_MARKET_CONTEXT: 'Bearish context',
    STOP_EXIT: 'Stop exit',
    CONTRACTION_VOLUME_NOT_BELOW_BASELINE: 'No volume dry-up',
  };

  return <Card sx={{ mt: 3 }}><CardContent>
    <Typography variant="h6" fontWeight={700}>Strategy intelligence · baseline diagnostics</Typography>
    <Typography variant="body2" color="text.secondary">
      Non-gating feature measurements and trade-path observations. They do not change candidate eligibility.
    </Typography>
    {error && <Alert severity="warning" sx={{ mt: 1 }}>{error}</Alert>}
    {!report && !error && <CircularProgress size={22} sx={{ mt: 2 }} />}
    {report && !report.available && <Alert severity="info" sx={{ mt: 1 }}>No diagnostic report is available. Generate it from the frozen baseline without overwriting historical results.</Alert>}
    {report?.available && <>
      <Alert severity="warning" sx={{ mt: 2 }}>
        Descriptive six-month sample: {String(report.trade_count)} trades, {String(metrics?.win_rate_pct ?? '—')}% win rate. This is not untouched out-of-sample validation and is not evidence of an improvement.
      </Alert>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(5, 1fr)' }, gap: 1, mt: 2 }}>
        {[
          ['Average MFE', number(summary?.average_mfe_r) + 'R'],
          ['Average MAE', number(summary?.average_mae_r) + 'R'],
          ['Reached 1R', String(summary?.threshold_touch_counts.reached_1r ?? 0) + ' / ' + String(report.trade_count)],
          ['Reached 2R', String(summary?.threshold_touch_counts.reached_2r ?? 0) + ' / ' + String(report.trade_count)],
          ['Censored', String(summary?.censored_at_test_end ?? 0)],
        ].map(([label, value]) => <Card variant="outlined" key={label}><CardContent sx={{ p: '12px !important' }}>
          <Typography variant="caption" color="text.secondary">{label}</Typography>
          <Typography fontWeight={700}>{value}</Typography>
        </CardContent></Card>)}
      </Box>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 2 }}>
        {Object.entries(report.loss_tag_counts ?? {}).map(([tag, count]) =>
          <Chip key={tag} size="small" variant="outlined" label={tagLabels[tag] + ': ' + count} />)}
        {report.experiment_status && <Chip size="small" color="warning" label="Walk-forward blocked · no untouched OOS" />}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        Loss tags overlap and describe context, not causes. RS percentiles rank the legacy weighted score among point-in-time eligible symbols; they are not Minervini RS ratings. Sector history is unavailable.
      </Typography>
      <Box sx={{ overflowX: 'auto', mt: 2 }}>
        <Table size="small"><TableHead><TableRow>
          <TableCell>Signal</TableCell><TableCell>Regime</TableCell><TableCell>RS rank</TableCell>
          <TableCell>VCP depths</TableCell><TableCell>Vol ratio</TableCell><TableCell>MFE / MAE</TableCell>
          <TableCell>Exit / tags</TableCell>
        </TableRow></TableHead><TableBody>
          {(report.trades ?? []).map(trade => <TableRow key={trade.symbol + '-' + trade.signal_date}>
            <TableCell>{trade.symbol}<Typography variant="caption" display="block" color="text.secondary">{trade.signal_date}</Typography></TableCell>
            <TableCell>{trade.market_regime}</TableCell>
            <TableCell>{trade.rs_percentile == null ? '—' : number(trade.rs_percentile, 1) + '%'}</TableCell>
            <TableCell>{trade.contraction_depths_pct.map(value => number(value, 1)).join(' → ') || '—'}</TableCell>
            <TableCell>{number(trade.contraction_volume_ratio, 2)}</TableCell>
            <TableCell>{number(trade.mfe_r)}R / {number(trade.mae_r)}R</TableCell>
            <TableCell>
              {trade.exit_reason}
              {trade.loss_tags.map(tag => <Typography key={tag} variant="caption" display="block">{tagLabels[tag] ?? tag}</Typography>)}
              {trade.censored_at_test_end && <Typography variant="caption" display="block" color="warning.main">End-of-test mark</Typography>}
            </TableCell>
          </TableRow>)}
        </TableBody></Table>
      </Box>
    </>}
  </CardContent></Card>;
}

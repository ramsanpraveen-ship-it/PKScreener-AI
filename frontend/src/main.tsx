import React from 'react';
import ReactDOM from 'react-dom/client';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import App from './App';
import './styles.css';

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#0b1018', paper: '#111a26' },
    primary: { main: '#62d4c5' },
    secondary: { main: '#94a8ff' },
    success: { main: '#5bd6a2' },
    warning: { main: '#f0b85a' },
    error: { main: '#ff7585' },
    text: { primary: '#edf3fb', secondary: '#97a8bc' },
  },
  shape: { borderRadius: 12 },
  typography: { fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' },
  components: {
    MuiCard: { styleOverrides: { root: { border: '1px solid #243244', backgroundImage: 'none' } } },
    MuiTableCell: { styleOverrides: { root: { borderColor: '#243244' } } },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);

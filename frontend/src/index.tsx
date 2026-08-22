import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Error tracking is opt-in via runtime config; the SDK loads as a separate
// chunk only when a DSN is configured, so unconfigured deployments pay
// nothing.
const sentryDsn = window.__MEDISENSE_CONFIG__?.SENTRY_DSN;
if (sentryDsn) {
  import('@sentry/react')
    .then((Sentry) => Sentry.init({ dsn: sentryDsn, sendDefaultPii: false }))
    .catch(() => undefined);
}

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

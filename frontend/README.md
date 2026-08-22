# MediSense Frontend

React 18 + TypeScript clinician UI for the MediSense backend. Vite
toolchain (`strict` + `noUnusedLocals`); production build outputs to
`build/` and is served by nginx in Docker, which also proxies REST and
WebSockets to the backend so the app runs same-origin.

## Scripts

```bash
npm start          # dev server on :3000 (alias: npm run dev)
npm test           # vitest unit tests
npm run build      # production build -> build/
npm run gen:api    # regenerate src/api/schema.d.ts from ../openapi.json
npm run e2e:demo   # Playwright E2E, demo mode
npm run e2e:clinical  # Playwright E2E, clinical mode (login gate)
npm run preview    # serve the production build locally
```

CI enforces that `src/api/schema.d.ts` is fresh against the committed
`openapi.json` — after any backend contract change, run `gen:api` and
commit the result.

## Configuration

Resolution order (see `src/config/api.ts`):

1. **Runtime**: `public/config.js` sets `window.__MEDISENSE_CONFIG__`;
   the Docker entrypoint templates it at container start, so one build
   runs against any backend. An empty `API_URL` means same-origin
   (the nginx-proxied deployment).
2. **Build time**: `VITE_API_URL` (and `VITE_ENABLE_*` feature flags,
   `VITE_DEBUG` for request/response console logging).
3. **Default**: `http://localhost:8000` for local dev.

## Authentication

Clinical mode uses httpOnly session cookies with double-submit CSRF:
`src/services/api.ts` sends `withCredentials` and echoes the CSRF cookie
into `X-CSRF-Token` on mutating requests. No tokens are stored in
localStorage. WebSockets authenticate with short-lived tickets fetched
from `/auth/ws-ticket`.

## Structure

```
src/
  api/schema.d.ts     generated API types (do not edit by hand)
  config/api.ts       runtime/build-time config resolution
  services/api.ts     axios instance, CSRF interceptor, endpoint wrappers
  lib/
    reportMapper.ts   backend response -> ClinicalReport (pure, unit-tested)
    wsClient.ts       live-case WS + HUD normalization (unit-tested)
    pcmTranscriber.ts AudioWorklet -> 16 kHz PCM -> /ws/transcribe
    transcriber.ts    browser Web Speech fallback
  hooks/
    useLiveCase.ts    live-case lifecycle: creation, WS, HUD/confidence
                      history, question feedback, finalize + report polling
  components/
    ClinicalInterface.tsx  container: state + view switching
    AppHeader.tsx          title, mode chip, demo-only toggles
    LoginModal.tsx         clinical-mode sign-in (password or OIDC)
    LiveAnalysisPanel.tsx  live HUD: differential, confidence sparkline,
                           question feedback, final report, PDF export
                           (print stylesheet)
    CaseHistory.tsx        persisted-case list + timeline (needs backend
                           CASE_DB_URL)
    KnowledgeBaseToggle.tsx KB status panel (real store facts)
    PatientForm, VoiceRecorder, ConversationChat, DifferentialDiagnosis,
    RedFlagAlerts, XAIExplanation, ClinicalReportView, LiveCoach, ...
e2e/
  demo/               boot, quick analysis, a11y (axe-core), fake-mic
                      voice flow driving the real STT pipeline
  clinical/           login gate: rejects bad credentials, cookie session
```

## Testing notes

- Unit tests cover the pure mapping layers (`lib/`); components are
  covered by Playwright, not unit tests.
- E2E starts the real backend (`../.venv`) and serves the production
  `build/` — **rebuild before re-running E2E after source changes**.
- The voice spec uses Chromium fake-media flags with a committed WAV
  fixture (`e2e/fixtures/utterance.wav`), so the full mic → WS → STT →
  HUD path runs headlessly with no microphone.

import path from 'path';
import { test, expect } from '@playwright/test';

/**
 * Live voice flow end-to-end: fake microphone -> AudioWorklet PCM ->
 * /ws/transcribe (server-side STT) -> transcript -> live case WS -> HUD.
 *
 * Chromium's fake capture device plays a committed espeak-generated WAV
 * ("persistent cough ... high fever ..."), which the tiny.en model
 * transcribes near-verbatim (validated at fixture-creation time), so the
 * assertions check real recognized keywords, not just plumbing.
 */

const FIXTURE = path.resolve(__dirname, '..', 'fixtures', 'utterance.wav');

test.use({
  permissions: ['microphone'],
  launchOptions: {
    ...(process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {}),
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      `--use-file-for-fake-audio-capture=${FIXTURE}`,
    ],
  },
});

test.describe('live voice flow', () => {
  test('fake mic speech reaches the transcript and drives the HUD', async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Clinical AI Assistant' })).toBeVisible();

    await page.getByRole('button', { name: 'Start Recording' }).click();
    await expect(page.getByRole('button', { name: 'Stop Recording' })).toBeVisible();

    // Server-side STT transcribes the fake-device audio; the utterance is
    // echoed into the conversation transcript via the live-case WS.
    await expect(page.getByText(/persistent cough/i).first()).toBeVisible({ timeout: 60_000 });

    // The recognized utterance recomputes the pipeline: the live HUD card
    // appears with a working diagnosis.
    await expect(page.getByText('Live RAG Analysis')).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText('Current Diagnosis')).toBeVisible({ timeout: 30_000 });

    await page.getByRole('button', { name: 'Stop Recording' }).click();
    // Post-stop UI: recording controls give way to playback of the captured
    // audio; the finalize action is available on the completed case.
    await expect(page.getByRole('button', { name: 'Stop Recording' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Play' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Generate Final Report' })).toBeVisible();
  });
});

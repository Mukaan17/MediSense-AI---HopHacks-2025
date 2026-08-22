# -*- coding: utf-8 -*-
"""WebSocket endpoints: live case HUD (/ws/case/{id}) and streaming
STT (/ws/transcribe). REST case lifecycle lives in routes/cases.py."""

import json
import logging
import asyncio
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.questioner_llm import (
    propose_questions_llm, stream_live_suggestions, parse_bullet_questions,
)
from core.llm_client import anthropic_available
from core.auth import user_from_ws_token

log = logging.getLogger("api")

from api.state import (
    _case_store,
    record_case_event,
)
from api.pipeline import (
    _apply_questions,
    _recompute_case,
)

router = APIRouter()

@router.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket):
    """Raw 16 kHz mono Int16 PCM frames in (binary), utterance transcripts
    out (JSON). A text frame {"event": "flush"} force-closes the current
    utterance (sent by the client on Stop Recording)."""
    from core.live_stt import UtteranceBuffer, transcribe_pcm, stt_executor, fw_available

    await ws.accept()
    if user_from_ws_token(ws.query_params.get("token")) is None:
        await ws.close(code=4401, reason="Authentication required")
        return
    if not await asyncio.get_running_loop().run_in_executor(stt_executor, fw_available):
        await ws.send_json({"error": "server-side transcription unavailable"})
        await ws.close()
        return
    # Readiness handshake: the client falls back to browser STT unless this
    # arrives, so an unavailable model degrades loudly instead of silently.
    await ws.send_json({"ready": True})

    buffer = UtteranceBuffer()
    loop = asyncio.get_running_loop()

    async def _emit(pcm: Optional[bytes]) -> None:
        if not pcm:
            return
        text = await loop.run_in_executor(stt_executor, transcribe_pcm, pcm)
        if text:
            await ws.send_json({"transcript": text, "final": True})

    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data:
                await _emit(buffer.add(data))
                continue
            text = message.get("text")
            if text:
                try:
                    event = json.loads(text)
                except Exception:
                    continue
                if event.get("event") == "flush":
                    await _emit(buffer.flush())
    except WebSocketDisconnect:
        return
    except Exception as e:
        log.warning(f"[STT] transcribe socket error: {e}")
        try:
            await ws.close()
        except Exception:
            pass

@router.websocket("/ws/case/{case_id}")
async def ws_case(ws: WebSocket, case_id: str):
    await ws.accept()
    if user_from_ws_token(ws.query_params.get("token")) is None:
        await ws.close(code=4401, reason="Authentication required")
        return
    case = _case_store.get(case_id)
    if case is None:
        await ws.send_json({"error": "case_id not found"})
        await ws.close()
        return

    async def _send_update(latest_utterance: Optional[str] = None,
                           latest_speaker: Optional[str] = None):
        # Heavy pipeline runs in a worker thread; the event loop stays free
        # for other connections.
        hud, question_state, _ = await asyncio.to_thread(
            _recompute_case, case, latest_utterance, latest_speaker)

        if question_state is not None:
            questions: List[Dict[str, Any]] = []
            if anthropic_available():
                try:
                    parts: List[str] = []
                    async for token in stream_live_suggestions(question_state):
                        parts.append(token)
                        await ws.send_json({"type": "streaming_token", "token": token})
                    questions = parse_bullet_questions("".join(parts), max_questions=3)
                except Exception as e:
                    log.warning(f"[coach] Claude streaming failed, falling back: {e}")
            if not questions:
                try:
                    questions = await asyncio.to_thread(propose_questions_llm, question_state, 3)
                except Exception as e:
                    log.warning(f"[coach] question generation failed: {e}")
            _apply_questions(hud, questions)

        record_case_event(case_id, "hud_update",
                          {"dx": hud.get("dx"), "conf": hud.get("conf")})
        await ws.send_json(hud)

    await _send_update()

    def _ingest(m: Dict[str, Any]):
        """Append one utterance to the case and persist immediately, so a
        disconnect mid-burst never loses received speech."""
        utt = m.get("utterance")
        speaker = m.get("speaker")
        if isinstance(utt, str) and utt.strip():
            prefixed = f"{speaker}: {utt.strip()}" if speaker in ("patient", "doctor") else utt.strip()
            case.setdefault("utterances", []).append(prefixed)
            _case_store.put(case_id, case)
            record_case_event(case_id, "utterance_added",
                              {"text": utt.strip()[:500], "speaker": speaker})
            return utt.strip(), speaker
        return None

    try:
        while True:
            msg = await ws.receive_json()
            ingested = [x for x in [_ingest(msg)] if x]
            # Collapse bursts: drain messages that arrived while the previous
            # recompute ran, so a fast talker triggers one recompute per burst
            # instead of one full pipeline per utterance.
            while True:
                try:
                    more = await asyncio.wait_for(ws.receive_json(), timeout=0.05)
                except asyncio.TimeoutError:
                    break
                got = _ingest(more)
                if got:
                    ingested.append(got)

            if ingested:
                # Echo every drained utterance to the transcript; only the
                # last one rides along with the recomputed HUD.
                for utt, speaker in ingested[:-1]:
                    await ws.send_json({"transcript_chunk": {"speaker": (speaker or "unknown"), "text": utt}})
                latest_utt, latest_speaker = ingested[-1]
                await _send_update(latest_utterance=latest_utt, latest_speaker=latest_speaker)
    except WebSocketDisconnect:
        return
    except Exception as e:
        await ws.send_json({"error": str(e)})
        await ws.close()

# -*- coding: utf-8 -*-
"""Background worker (arq over the existing Redis). Run with:

    arq worker.settings.WorkerSettings

Queue mode is opt-in: the API enqueues finalize jobs only when
FINALIZE_MODE=queue and REDIS_URL is reachable; otherwise reports are
generated inline exactly as before.
"""

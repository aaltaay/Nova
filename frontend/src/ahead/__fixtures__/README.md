# Ahead wire fixtures

Made-up answers (ticker XYZ, invented numbers, model `model-a`) for every state of `GET /api/ahead/forecast/{symbol}`
and `GET /api/ahead/status`. Both sides read them: Vitest (`aheadApi.test.ts`) and pytest
(`backend/tests/test_ahead_wire.py`, which checks `ahead.view` builds the same keys and types). Change the wire here,
in `aheadTypes.ts`, in `backend/ahead/view.py` and in `architecture/schema/ahead.md` together.

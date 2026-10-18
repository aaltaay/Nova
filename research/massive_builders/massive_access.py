"""Is Massive still serving its files? Research tooling.

Operator, 2026-10-09: "am i good to cancel massive subscription? we dont need it anymore?" -- then "figure it out". Cancelled,
the downloads should end on their own and quietly: once Massive refuses its files for good, the supervisor starts no more
fetchers and no reference runs, the page says what is on disk and that nothing more comes, and a resubscribe brings everything
back with no one touching anything (the next served answer turns it all on again and the missing days are fetched).

The supervisor asks every 30 minutes (every 2 hours once ended): one listing of this month's and last month's day bars and a
one-byte read of the newest. An answer of 401 / 403 (AccessDenied, InvalidAccessKeyId, SignatureDoesNotMatch) is a refusal; a
network error or a timeout says nothing either way. Ended = refused on every ask for 6 hours and at least 4 asks in a row: on
2026-10-05 Massive answered 403 to a burst of requests and served the same files a minute later, so a refusal alone is never the end.

State: <NOVA_MARKET_DATA_DIR>/access.json
    {schema_version: 1, state: "live" | "ended", last_ok, last_ok_file, refused_since, refused_n, last_probe, last_result,
     last_reason, ended_at}   (times are epoch seconds; a file with another schema_version is read as live and rewritten)

    py -3 research/massive_builders/massive_access.py           ask once now and print the state
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import massive_bucket as mf  # noqa: E402
from massive_env import NY, ROOT  # noqa: E402

STATE = ROOT / "access.json"
SCHEMA_VERSION = 1
ASK_EVERY = 1800                 # while live, or while refusals are being counted
ASK_EVERY_ENDED = 2 * 3600       # while ended: how soon a resubscribe is noticed
ENDED_AFTER = 6 * 3600           # refused for this long ...
ENDED_ASKS = 4                   # ... and at least this many asks in a row
REFUSED_CODES = {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "Forbidden", "Unauthorized", "NotAuthorized"}


def fresh() -> dict:
    return {"schema_version": SCHEMA_VERSION, "state": "live", "last_ok": None, "last_ok_file": None, "refused_since": None,
            "refused_n": 0, "last_probe": None, "last_result": None, "last_reason": None, "ended_at": None}


def load() -> dict:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fresh()
    return st if st.get("schema_version") == SCHEMA_VERSION else fresh()


def save(st: dict) -> None:
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(st, indent=1), encoding="utf-8"); tmp.replace(STATE)


def ended() -> bool:
    return load().get("state") == "ended"


def probe() -> tuple[str, str]:
    """("ok" | "refused" | "unknown", why). Never raises."""
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        s3 = mf.client()
        today = date.today(); last = today.replace(day=1) - timedelta(days=1)
        keys: list[str] = []
        for d in (today, last):
            r = s3.list_objects_v2(Bucket=mf.BUCKET, Prefix=f"{mf.PREFIX}/day_aggs_v1/{d.year}/{d.month:02d}/")
            keys += [o["Key"] for o in r.get("Contents", [])]
        if not keys:
            return "unknown", "no day bars listed for this month or last"
        newest = max(keys)
        s3.get_object(Bucket=mf.BUCKET, Key=newest, Range="bytes=0-0")["Body"].read()
        return "ok", newest.rsplit("/", 1)[-1]
    except ClientError as exc:
        err = exc.response.get("Error", {}); code = str(err.get("Code", "")); status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        why = f"HTTP {status} {code}: {str(err.get('Message', ''))[:120]}".strip()
        return ("refused" if status in (401, 403) or code in REFUSED_CODES else "unknown"), why
    except (BotoCoreError, OSError) as exc:
        return "unknown", f"{type(exc).__name__}: {str(exc)[:160]}"
    except SystemExit as exc:            # mf.client() exits when no S3 key pair is configured: nothing is served without one
        return "refused", str(exc)


def ask(log=print, now: float | None = None) -> dict:
    """Ask Massive once, update the state file, and say so in the log when the state changes."""
    now = now or time.time(); st = load()
    res, why = probe()
    st.update(last_probe=now, last_result=res, last_reason=why)
    if res == "ok":
        if st["state"] == "ended":
            log("Massive serves its files again: the downloads start again and fetch every day that is missing")
        elif st["refused_n"]:
            log(f"Massive serves its files again after {st['refused_n']} refused ask(s)")
        st.update(state="live", last_ok=now, last_ok_file=why, refused_since=None, refused_n=0, ended_at=None)
    elif res == "refused":
        st["refused_since"] = st["refused_since"] or now; st["refused_n"] += 1
        if st["state"] != "ended":
            log(f"Massive refused its files ({why}); ask {st['refused_n']} of at least {ENDED_ASKS}, refused since "
                f"{datetime.fromtimestamp(st['refused_since'], NY):%Y-%m-%d %H:%M} ET")
            if st["refused_n"] >= ENDED_ASKS and now - st["refused_since"] >= ENDED_AFTER:
                st.update(state="ended", ended_at=now)
                log("Massive access has ENDED (refused for 6 hours): no more fetchers or reference runs; the files on disk stay as they are")
    save(st)
    return st


def worker(log) -> None:
    """Thread in the supervisor: ask, wait, ask again."""
    while True:
        try:
            st = ask(log)
        except Exception as exc:  # noqa: BLE001 - a state file that cannot be written is said once a round; the next ask tries again
            log(f"access check failed: {type(exc).__name__}: {str(exc)[:160]}"); st = load()
        time.sleep(ASK_EVERY_ENDED if st.get("state") == "ended" else ASK_EVERY)


def describe(st: dict) -> str:
    def t(x):
        return datetime.fromtimestamp(x, NY).strftime("%Y-%m-%d %H:%M ET") if x else "never"
    return (f"state {st['state']} | last served {t(st['last_ok'])} ({st['last_ok_file']}) | refused {st['refused_n']} time(s) since "
            f"{t(st['refused_since'])} | last ask {t(st['last_probe'])}: {st['last_result']} {st['last_reason'] or ''}"
            + (f" | ended {t(st['ended_at'])}" if st["ended_at"] else ""))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__); raise SystemExit(0)
    print(describe(ask()))

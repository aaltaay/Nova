"""python -m nova_brain -- standing Windows/Linux client next to Nova."""
from __future__ import annotations

from dotenv import load_dotenv

from nova_brain.loop import run_forever
from paths import env_file_path

if __name__ == "__main__":
    load_dotenv(env_file_path())
    run_forever()

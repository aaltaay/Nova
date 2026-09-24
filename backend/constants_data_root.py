"""Where Nova keeps its data: on the operator's F: drive, never C: (operator ask, 2026-09-24).

``tools/data_root.py move`` puts this checkout's ``backend/.cache`` and
``backend/logs`` on F: behind directory junctions; the diagnostics
``data_folders`` row reports the real drive of every data folder.
"""
DATA_DRIVE_WIN = "F:"                          # the operator's data drive
DATA_CACHE_TARGET_WIN = r"F:\Nova\cache"       # backend\.cache lives here once moved
DATA_LOGS_TARGET_WIN = r"F:\Nova\logs"         # backend\logs lives here once moved
DATA_SYSTEM_DRIVE_DEFAULT = "C:"               # when SystemDrive is not set
DATA_ROOT_SCHEMA_VERSION = 1                   # tools/data_root.py status --json
DATA_MOVE_COMMAND = "py -3 tools/data_root.py move"
DATA_MOVE_API_PORT = 8000                      # the API holds files in backend\.cache
DATA_MOVE_UI_PORT = 5173                       # the UI window holds backend\logs\ui-console.log
DATA_MOVE_MTIME_SLACK_SEC = 2.0                # a verified copy keeps its modified time (copy2)
DATA_MOVED_SUFFIX = ".moved-"                  # backend\.cache.moved-<stamp>: the C: original, until verified

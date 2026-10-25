"""`python -m wastatus`.

The `.env` file is read here, before `cli` is imported, and not inside `main`.
Some settings are read at import time rather than when they are used, so a file
read any later would be read too late to matter. Importing this package on its own
still changes nothing about the process: only running it does.
"""

from .env import load

load()

from .cli import main  # noqa: E402  imported after the file is read, on purpose

raise SystemExit(main())

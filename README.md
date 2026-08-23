# Video GenSystem

Desktop/local production platform that turns prepared scripts and voiceovers into a media package for DaVinci Resolve.

## Stack

- Python 3.11+
- Streamlit for the MVP desktop UI
- SQLAlchemy 2.x and SQLite
- Alembic migrations
- FFmpeg/FFprobe and ComfyUI integrations in later phases

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app --version
pytest
```

The default database is `data/app.db`. Override it with `VIDEO_GENSYSTEM_DATABASE_URL`, using a SQLAlchemy URL such as `sqlite:///D:/video_gensystem/data/app.db`.

## Foundation guarantees

- Every SQLite connection enables foreign keys, requests WAL mode, and sets a 5000 ms busy timeout.
- Asset versions are immutable by convention and only one chosen asset may exist per shot/type.
- Episode asset paths are relative, normalized with `/`, and may not escape the episode root.
- Shot character invariants are validated in the application layer.


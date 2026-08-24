# Video GenSystem

Desktop/local production platform that turns prepared scripts and voiceovers into a media package for DaVinci Resolve.

The platform is domain-agnostic and supports any series or subject. Historical series and episode names used in tests are examples only; production services contain no story-specific logic.

## Stack

- Python 3.11+
- Streamlit for the MVP desktop UI
- SQLAlchemy 2.x and SQLite
- Alembic migrations
- FFmpeg/FFprobe and ComfyUI integrations in later phases

## Setup

Conda is the recommended environment manager. Python packages remain declared in `pyproject.toml`; `environment.yml` also provisions SQLite and FFmpeg/FFprobe for local development.

```powershell
conda env create -f environment.yml
conda activate video-gensystem
python -m pip install -e . --no-deps
alembic upgrade head
python -m app --version
pytest
```

Update an existing environment after changing `environment.yml`:

```powershell
conda env update -f environment.yml --prune
```

ComfyUI and GPU-specific PyTorch/CUDA packages are intentionally kept outside this shared environment. Their versions depend on the installed NVIDIA driver and the selected ComfyUI workflow. A standard `.venv` remains a supported fallback when Conda is unavailable.

The default database is `data/app.db`. Override it with `VIDEO_GENSYSTEM_DATABASE_URL`, using a SQLAlchemy URL such as `sqlite:///D:/video_gensystem/data/app.db`.

FFprobe is provided by the Conda `ffmpeg` package. If it is not on PATH, set its executable explicitly:

```powershell
$env:VIDEO_GENSYSTEM_FFPROBE_PATH = "C:\path\to\ffprobe.exe"
```

Reference CLI example:

```powershell
python cli.py reference create --name "Character Example" --slug character_example --type character --scope shared_across_series
python cli.py reference add-version --reference-id 1 --file .\reference.png --library-root .\library
python cli.py reference list-versions --reference-id 1
```

## Foundation guarantees

- Every SQLite connection enables foreign keys, requests WAL mode, and sets a 5000 ms busy timeout.
- Asset versions are immutable by convention and only one chosen asset may exist per shot/type.
- Episode asset paths are relative, normalized with `/`, and may not escape the episode root.
- Shot character invariants are validated in the application layer.

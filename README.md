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
$env:VIDEO_GENSYSTEM_FFMPEG_PATH = "C:\path\to\ffmpeg.exe"
```

Reference CLI example:

```powershell
python cli.py reference create --name "Character Example" --slug character_example --type character --scope shared_across_series
python cli.py reference add-version --reference-id 1 --file .\reference.png --library-root .\library
python cli.py reference list-versions --reference-id 1
```

## Run the Streamlit UI

```powershell
conda activate video-gensystem
$env:VIDEO_GENSYSTEM_LIBRARY_ROOT = "D:\video_gensystem\library"
streamlit run streamlit_app.py
```

The current MVP screens are Series, Episodes, Import, Shot Manager, References, Image Gallery, and Motion Queue. Local path inputs are available for desktop workflows; upload controls remain available for scripts, multiple WAV files, and reference versions.

## SQLite job queue

Queue operations live under `app.queue`. Jobs are ordered by `high`, `normal`, `image`, `gpu`, `overnight`, then `export`, with FIFO ordering inside each priority. Worker claims use a dedicated SQLite connection and `BEGIN IMMEDIATE`; job processing starts only after the claim transaction commits. Stale jobs default to a 30-minute timeout and are requeued while attempts remain.

## Image providers

- Google image generation uses the bundled `integrations/h2dev_flow_extension` to control the user's signed-in Google Flow UI. It does not call Gemini API. Set `VIDEO_GENSYSTEM_FLOW_BRIDGE_TOKEN`, reload the unpacked extension, then enable its localhost bridge using the same token.
- If Chrome uses a custom Downloads directory, set `VIDEO_GENSYSTEM_FLOW_DOWNLOADS_ROOT` to that absolute path (for example `D:\Download`). Flow may serve JPEG/WebP even when the requested filename ends in `.png`; the provider converts these downloads to managed PNG assets.
- ComfyUI defaults to `http://127.0.0.1:8188` and accepts a workflow exported in API format. Use `{{PROMPT}}` in the workflow or configure a prompt node; map pinned references to LoadImage nodes with `reference_image_nodes`.
- Manual fallback copies an existing PNG into managed episode storage without overwriting the source.

The Image Gallery queues work. Run image jobs from Python with `app.workers.image_gen.run_image_worker`; generated variations are immutable Asset versions and are not chosen automatically.

## Motion providers

- `render_kenburns` renders deterministic H.264 MP4 clips with FFmpeg `zoompan`; video duration, frame count, FPS, dimensions and codec are verified through FFprobe.
- `wan_local` runs an image-to-video ComfyUI workflow. Configure the API workflow, prompt node and source-image node in Motion Queue.
- `veo_cloud` uses the optional Google GenAI SDK and defaults to `veo-3.1-generate-preview`; install it with `python -m pip install -e ".[veo]"`. It is optional and does not block the local Wan/Ken Burns workflow.
- Motion fill defaults to `extend`; `loop` must be explicit and `split` produces deterministic sub-shot plans. Three generative failures fall through sprite support to Ken Burns so a Shot is never silently empty.

Run queued motion jobs with `app.workers.motion_gen.run_motion_worker`. Motion variations are immutable `video` Assets and become selected only through Motion Queue.

## Foundation guarantees

- Every SQLite connection enables foreign keys, requests WAL mode, and sets a 5000 ms busy timeout.
- Asset versions are immutable by convention and only one chosen asset may exist per shot/type.
- Episode asset paths are relative, normalized with `/`, and may not escape the episode root.
- Shot character invariants are validated in the application layer.
- Concurrent workers atomically claim each job at most once and retry SQLite lock contention with exponential backoff plus jitter.

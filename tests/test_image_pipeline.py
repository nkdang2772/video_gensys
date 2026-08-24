from __future__ import annotations

import base64
import json
import socket
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, Episode, EpisodeReferencePin, Job, Reference, ReferenceVersion, Series, Shot
from app.providers.image import ComfyUIImageProvider, GoogleFlowImageProvider, ImageProvider, ManualImageProvider
from app.providers.image.base import ProviderCost, ProviderTimeoutError, output_path, write_png_atomic
from app.services.character_batch import compute_batch_key
from app.services.image_generation import choose_image_asset, enqueue_character_batch, enqueue_image_job
from app.workers.image_gen import run_image_worker

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def _episode(session: Session, tmp_path: Path, *, shot_count: int = 1) -> tuple[Episode, list[Shot]]:
    root = tmp_path / "library" / "episode"
    (root / "images" / "generated").mkdir(parents=True)
    series = Series(slug="generic-series", name="Generic Series")
    episode = Episode(
        series=series,
        episode_number=1,
        slug="generic-episode",
        title="Generic Episode",
        effective_resolution="1920x1080",
        effective_fps=30,
        effective_aspect_ratio="16:9",
        root_path=str(root),
    )
    shots = [
        Shot(
            episode=episode,
            shot_id=f"s{number:03d}",
            order_index=number,
            visual_description=f"Generic visual {number}",
            characters_json=["character-a"] if number % 2 else ["character-b"],
            character_batch_key=compute_batch_key(
                ["character-a"] if number % 2 else ["character-b"]
            ),
        )
        for number in range(1, shot_count + 1)
    ]
    session.add_all([episode, *shots])
    session.flush()
    return episode, shots


class RecordingProvider(ImageProvider):
    name = "manual"

    def __init__(self, *, timeout_calls: int = 0) -> None:
        self.timeout_calls = timeout_calls
        self.calls = 0
        self.references: list[list[Path]] = []

    def generate(self, prompt, reference_images, config):
        self.calls += 1
        self.references.append(list(reference_images))
        if self.calls <= self.timeout_calls:
            raise ProviderTimeoutError("simulated timeout")
        return write_png_atomic(output_path(config), PNG_BYTES)

    def cost(self, config):
        del config
        return ProviderCost(usd=0.25, is_estimated=True)


def test_all_three_image_provider_adapters_generate_png(tmp_path, monkeypatch) -> None:
    source = tmp_path / "manual.png"
    source.write_bytes(PNG_BYTES)
    manual_output = ManualImageProvider().generate(
        "ignored", [], {"source_path": str(source), "output_path": str(tmp_path / "manual-out.png")}
    )
    assert manual_output.read_bytes() == PNG_BYTES

    with socket.socket() as available_port:
        available_port.bind(("127.0.0.1", 0))
        bridge_port = available_port.getsockname()[1]
    bridge_token = "test-flow-bridge-token-123"
    downloads_root = tmp_path / "Downloads"
    observed_task = {}

    def simulate_extension() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                request = Request(
                    f"http://127.0.0.1:{bridge_port}/v1/tasks/next",
                    headers={"X-VideoGenSystem-Token": bridge_token},
                )
                with urlopen(request, timeout=1) as response:
                    if response.status == 204:
                        time.sleep(0.01)
                        continue
                    task = json.loads(response.read().decode())
                observed_task.update(task)
                downloaded = downloads_root / Path(task["download_path"])
                downloaded.parent.mkdir(parents=True)
                downloaded.write_bytes(PNG_BYTES)
                result = Request(
                    f"http://127.0.0.1:{bridge_port}/v1/tasks/{task['id']}/result",
                    data=json.dumps({"ok": True, "download_path": task["download_path"]}).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "X-VideoGenSystem-Token": bridge_token,
                    },
                    method="POST",
                )
                with urlopen(result, timeout=1) as response:
                    assert response.status == 200
                return
            except (URLError, ConnectionError, TimeoutError):
                time.sleep(0.01)
        raise AssertionError("Flow bridge did not become available")

    extension_thread = threading.Thread(target=simulate_extension)
    extension_thread.start()
    google_output = GoogleFlowImageProvider(bridge_token=bridge_token).generate(
        "A generic scene",
        [source],
        {
            "output_path": str(tmp_path / "google-flow.png"),
            "downloads_root": str(downloads_root),
            "bridge_port": bridge_port,
            "timeout_sec": 5,
        },
    )
    extension_thread.join(timeout=5)
    assert not extension_thread.is_alive()
    assert google_output.read_bytes() == PNG_BYTES
    assert observed_task["prompt"] == "A generic scene"
    assert observed_task["references"][0]["data_url"].startswith("data:image/png;base64,")
    assert not (downloads_root / observed_task["download_path"]).exists()

    comfy_requests = []

    def fake_request(url, *, payload, timeout):
        comfy_requests.append((url, payload, timeout))
        if url.endswith("/prompt"):
            assert payload["prompt"]["1"]["inputs"]["text"] == "A generic scene"
            assert payload["prompt"]["2"]["inputs"]["image"] == "uploaded/reference.png"
            return json.dumps({"prompt_id": "prompt-1"}).encode()
        if "/history/" in url:
            return json.dumps(
                {
                    "prompt-1": {
                        "outputs": {
                            "9": {"images": [{"filename": "result.png", "subfolder": "", "type": "output"}]}
                        }
                    }
                }
            ).encode()
        if "/view?" in url:
            return PNG_BYTES
        raise AssertionError(url)

    monkeypatch.setattr("app.providers.image.comfyui._request", fake_request)
    monkeypatch.setattr(
        "app.providers.image.comfyui._upload_image",
        lambda _base, _source, _timeout: "uploaded/reference.png",
    )
    comfy_output = ComfyUIImageProvider().generate(
        "A generic scene",
        [source],
        {
            "output_path": str(tmp_path / "comfy.png"),
            "workflow": {
                "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{PROMPT}}"}},
                "2": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}},
            },
            "reference_image_nodes": [{"node_id": "2", "input": "image"}],
            "poll_interval_sec": 0,
        },
    )
    assert comfy_output.read_bytes() == PNG_BYTES
    assert len(comfy_requests) == 3


def test_image_worker_creates_ten_asset_versions_and_cost(engine, tmp_path) -> None:
    with Session(engine) as session, session.begin():
        episode, shots = _episode(session, tmp_path, shot_count=10)
        for shot in shots:
            enqueue_image_job(session, shot_id=shot.id, provider="manual")
    provider = RecordingProvider()
    processed = run_image_worker(
        engine,
        library_root=tmp_path / "library",
        providers={"manual": provider},
        exit_when_empty=True,
    )
    assert processed == 10
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 10
        assets = list(session.scalars(select(Asset).order_by(Asset.shot_id)))
        assert all(asset.version == 1 and not asset.is_chosen for asset in assets)
        jobs = list(session.scalars(select(Job).order_by(Job.id)))
        assert all(job.status == "done" and job.cost_usd == 0.25 for job in jobs)
        assert all(job.cost_is_estimated for job in jobs)


def test_image_worker_retries_provider_timeout_and_uses_pinned_version(engine, tmp_path) -> None:
    library_root = tmp_path / "library"
    reference_file = library_root / "references_shared" / "characters" / "character-a.png"
    reference_file.parent.mkdir(parents=True)
    reference_file.write_bytes(PNG_BYTES)
    with Session(engine) as session, session.begin():
        episode, shots = _episode(session, tmp_path)
        reference = Reference(
            slug="character-a",
            name="Character A",
            reference_type="character",
            scope="shared_across_series",
            current_version=1,
        )
        version = ReferenceVersion(
            reference=reference,
            version=1,
            file_path=reference_file.relative_to(library_root).as_posix(),
            checksum="fixture",
        )
        session.add(EpisodeReferencePin(episode=episode, reference=reference, reference_version=version))
        session.flush()
        job = enqueue_image_job(
            session,
            shot_id=shots[0].id,
            provider="manual",
            max_attempts=3,
        )
        job_id = job.id
        version_id = version.id
    provider = RecordingProvider(timeout_calls=2)
    attempts = run_image_worker(
        engine,
        library_root=library_root,
        providers={"manual": provider},
        exit_when_empty=True,
    )
    assert attempts == 3
    assert provider.calls == 3
    assert provider.references[-1] == [reference_file.resolve()]
    with Session(engine) as session:
        completed = session.get(Job, job_id)
        assert completed is not None
        assert completed.status == "done"
        assert completed.attempt_count == 2
        assert completed.input_payload_json["reference_version_ids"] == [version_id]
        assert session.scalar(select(func.count()).select_from(Asset)) == 1


def test_explicit_empty_provider_registry_never_uses_defaults(engine, tmp_path, monkeypatch) -> None:
    with Session(engine) as session, session.begin():
        _episode_record, shots = _episode(session, tmp_path)
        job = enqueue_image_job(session, shot_id=shots[0].id, provider="google_flow")
        job_id = job.id
    monkeypatch.setattr(
        "app.workers.image_gen.default_image_providers",
        lambda: (_ for _ in ()).throw(AssertionError("default providers must not be created")),
    )
    processed = run_image_worker(
        engine,
        library_root=tmp_path / "library",
        providers={},
        exit_when_empty=True,
    )
    assert processed == 1
    with Session(engine) as session:
        failed = session.get(Job, job_id)
        assert failed is not None
        assert failed.status == "failed"
        assert "provider is unavailable" in (failed.error_message or "")


def test_legacy_google_provider_id_is_normalized(session, tmp_path) -> None:
    _episode_record, shots = _episode(session, tmp_path)
    job = enqueue_image_job(session, shot_id=shots[0].id, provider="google")
    assert job.input_payload_json["provider"] == "google_flow"


def test_character_batch_queues_and_generates_eighty_generic_shots(engine, tmp_path) -> None:
    source = tmp_path / "batch-source.png"
    source.write_bytes(PNG_BYTES)
    with Session(engine) as session, session.begin():
        episode, _shots = _episode(session, tmp_path, shot_count=80)
        jobs = enqueue_character_batch(
            session,
            episode_id=episode.id,
            provider="manual",
            config={"source_path": str(source)},
        )
        assert len(jobs) == 80
        batch_keys = [job.input_payload_json["character_batch_key"] for job in jobs]
        assert batch_keys == sorted(batch_keys)
        assert all(job.priority == "overnight" for job in jobs)
    processed = run_image_worker(
        engine,
        library_root=tmp_path / "library",
        providers={"manual": ManualImageProvider()},
        exit_when_empty=True,
    )
    assert processed == 80
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 80
        shot_count_with_assets = session.scalar(
            select(func.count(func.distinct(Asset.shot_id))).where(Asset.asset_type == "image")
        )
        assert shot_count_with_assets == 80


def test_choose_image_asset_switches_selection(session, tmp_path) -> None:
    episode, shots = _episode(session, tmp_path)
    first = Asset(
        episode=episode,
        shot=shots[0],
        asset_type="image",
        version=1,
        is_chosen=True,
        file_path="images/generated/v1.png",
    )
    second = Asset(
        episode=episode,
        shot=shots[0],
        asset_type="image",
        version=2,
        is_chosen=False,
        file_path="images/generated/v2.png",
    )
    session.add_all([first, second])
    session.commit()
    choose_image_asset(session, second.id)
    session.commit()
    assert not first.is_chosen
    assert second.is_chosen

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.media.ffprobe import probe_video
from app.models import Asset, Episode, Job, Series, Shot
from app.motion.fallback import render_with_fallback
from app.motion.fill import apply_fill_policy, plan_subshots
from app.motion.kenburns import KenBurnsError, render_kenburns
from app.providers.video import VeoVideoProvider, VideoProvider, VideoProviderError, WanVideoProvider
from app.providers.video.base import video_output_path
from app.services.motion_generation import choose_motion_asset, enqueue_motion_job, retry_motion_job
from app.workers.motion_gen import run_motion_worker


def make_image(path: Path, size: tuple[int, int] = (320, 180)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (40, 110, 170)).save(path)
    return path


def make_clip(
    tmp_path: Path,
    ffmpeg_executable: str,
    *,
    name: str = "clip.mp4",
    duration: float = 1.0,
    fps: float = 12.0,
) -> Path:
    return render_kenburns(
        make_image(tmp_path / f"{name}.png"),
        duration,
        output_path=tmp_path / name,
        fps=fps,
        ffmpeg_path=ffmpeg_executable,
    )


def make_episode(session: Session, tmp_path: Path, shot_count: int = 1) -> tuple[Episode, list[Shot]]:
    root = tmp_path / "library" / "episode"
    for folder in ("images/chosen", "clips/generated"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    series = Series(slug="motion-series", name="Motion Series")
    episode = Episode(
        series=series,
        episode_number=1,
        slug="motion-episode",
        title="Motion Episode",
        effective_resolution="320x180",
        effective_fps=12,
        effective_aspect_ratio="16:9",
        root_path=str(root),
    )
    shots = []
    for index in range(1, shot_count + 1):
        shot = Shot(
            episode=episode,
            shot_id=f"s{index:03d}",
            order_index=index,
            visual_description=f"Motion scene {index}",
            audio_duration_sec=1.0,
            motion_intent="generative",
            motion_provider="wan_local",
            motion_fill_policy="extend",
        )
        image_path = root / "images" / "chosen" / f"s{index:03d}.png"
        make_image(image_path)
        shot.assets.append(
            Asset(
                episode=episode,
                asset_type="image",
                version=1,
                is_chosen=True,
                file_path=image_path.relative_to(root).as_posix(),
            )
        )
        shots.append(shot)
    session.add_all([episode, *shots])
    session.flush()
    return episode, shots


class CopyVideoProvider(VideoProvider):
    name = "wan_local"

    def __init__(self, source: Path) -> None:
        self.source = source
        self.calls = 0

    def generate(self, source_image, prompt, config):
        del source_image, prompt
        self.calls += 1
        destination = video_output_path(config)
        shutil.copy2(self.source, destination)
        return destination


class FailingVideoProvider(VideoProvider):
    name = "wan_local"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, source_image, prompt, config):
        del source_image, prompt, config
        self.calls += 1
        raise VideoProviderError("simulated Wan failure")


def test_kenburns_renders_five_second_mp4(
    tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    output = render_kenburns(
        make_image(tmp_path / "source.png"),
        5.0,
        "left_to_right",
        1.0,
        1.1,
        output_path=tmp_path / "kenburns.mp4",
        fps=30,
        ffmpeg_path=ffmpeg_executable,
    )
    metadata = probe_video(output, ffprobe_path=ffprobe_executable)
    assert metadata.duration_sec == pytest.approx(5.0, abs=0.1)
    assert metadata.frame_rate == pytest.approx(30.0, abs=0.01)
    assert metadata.frame_count == 150
    assert (metadata.width, metadata.height) == (320, 180)
    assert metadata.codec == "h264"


def test_kenburns_rejects_existing_output_without_overwriting(tmp_path: Path) -> None:
    source = make_image(tmp_path / "source.png")
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"preserve-existing-output")

    with pytest.raises(KenBurnsError, match="already exists"):
        render_kenburns(source, 5.0, output_path=output)

    assert output.read_bytes() == b"preserve-existing-output"


def test_wan_comfyui_adapter_returns_real_mp4(
    tmp_path: Path, monkeypatch, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    source = make_image(tmp_path / "wan-source.png")
    expected = make_clip(tmp_path, ffmpeg_executable, duration=1.0)
    calls = []

    monkeypatch.setattr("app.providers.video.wan._upload_image", lambda *_args: "uploaded/source.png")

    def fake_request(url, *, payload, timeout):
        calls.append((url, payload, timeout))
        if url.endswith("/prompt"):
            assert payload["prompt"]["1"]["inputs"]["image"] == "uploaded/source.png"
            assert payload["prompt"]["2"]["inputs"]["text"] == "gentle movement"
            return b'{"prompt_id":"wan-1"}'
        if "/history/" in url:
            return b'{"wan-1":{"outputs":{"9":{"videos":[{"filename":"wan.mp4","type":"output"}]}}}}'
        if "/view?" in url:
            return expected.read_bytes()
        raise AssertionError(url)

    monkeypatch.setattr("app.providers.video.wan._request", fake_request)
    output = WanVideoProvider().generate(
        source,
        "gentle movement",
        {
            "workflow": {
                "1": {"inputs": {"image": ""}},
                "2": {"inputs": {"text": "{{PROMPT}}"}},
            },
            "source_image_node_id": "1",
            "output_path": str(tmp_path / "wan-output.mp4"),
            "poll_interval_sec": 0,
        },
    )
    metadata = probe_video(output, ffprobe_path=ffprobe_executable)
    assert metadata.frame_count == 12
    assert metadata.frame_rate == pytest.approx(12.0)
    assert any(url.endswith("/prompt") for url, *_ in calls)


def test_wan_rejects_invalid_mp4_without_leaving_output(tmp_path: Path, monkeypatch) -> None:
    source = make_image(tmp_path / "wan-invalid-source.png")
    output = tmp_path / "wan-invalid-output.mp4"
    monkeypatch.setattr("app.providers.video.wan._upload_image", lambda *_args: "source.png")

    def fake_request(url, *, payload, timeout):
        if url.endswith("/prompt"):
            return b'{"prompt_id":"wan-invalid"}'
        if "/history/" in url:
            return b'{"wan-invalid":{"outputs":{"9":{"videos":[{"filename":"broken.mp4"}]}}}}'
        if "/view?" in url:
            return b"not-an-mp4"
        raise AssertionError(url)

    monkeypatch.setattr("app.providers.video.wan._request", fake_request)

    with pytest.raises(VideoProviderError, match="valid MP4"):
        WanVideoProvider().generate(
            source,
            "gentle movement",
            {
                "workflow": {
                    "1": {"inputs": {"image": ""}},
                    "2": {"inputs": {"text": "{{PROMPT}}"}},
                },
                "source_image_node_id": "1",
                "output_path": str(output),
                "poll_interval_sec": 0,
            },
        )

    assert not output.exists()


def test_veo_adapter_uses_injected_client(tmp_path: Path, ffmpeg_executable: str) -> None:
    source = make_image(tmp_path / "veo-source.png")
    expected = make_clip(tmp_path, ffmpeg_executable, duration=1.0)

    class FakeVideo:
        def save(self, path):
            Path(path).write_bytes(expected.read_bytes())

    video = FakeVideo()
    operation = SimpleNamespace(
        done=True,
        response=SimpleNamespace(generated_videos=[SimpleNamespace(video=video)]),
    )
    client = SimpleNamespace(
        models=SimpleNamespace(generate_videos=lambda **_kwargs: operation),
        operations=SimpleNamespace(get=lambda item: item),
        files=SimpleNamespace(download=lambda **_kwargs: None),
    )
    output = VeoVideoProvider(client=client).generate(
        source,
        "slow camera move",
        {"output_path": str(tmp_path / "veo.mp4"), "poll_interval_sec": 0},
    )
    assert output.read_bytes() == expected.read_bytes()


def test_motion_fill_extend_split_and_loop(
    tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    clip = make_clip(tmp_path, ffmpeg_executable, duration=1.0)
    extended = apply_fill_policy(
        clip,
        2.5,
        "extend",
        output_path=tmp_path / "extended.mp4",
        ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable,
    )
    assert probe_video(extended.output_path, ffprobe_path=ffprobe_executable).duration_sec == pytest.approx(
        2.5, abs=0.1
    )
    split = apply_fill_policy(
        clip,
        5.0,
        "split",
        shot_id="s042",
        max_segment_duration_sec=2.0,
        ffprobe_path=ffprobe_executable,
    )
    assert [item.shot_id for item in split.subshots] == ["s042_01", "s042_02", "s042_03"]
    assert sum(item.duration_sec for item in split.subshots) == pytest.approx(5.0)
    looped = apply_fill_policy(
        clip,
        2.2,
        "loop",
        output_path=tmp_path / "looped.mp4",
        ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable,
    )
    assert probe_video(looped.output_path, ffprobe_path=ffprobe_executable).duration_sec == pytest.approx(
        2.2, abs=0.1
    )


def test_wan_failure_falls_back_to_kenburns(
    tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    provider = FailingVideoProvider()

    def broken_sprite(*_args, **_kwargs):
        raise RuntimeError("sprite unavailable")

    result = render_with_fallback(
        provider,
        make_image(tmp_path / "fallback.png"),
        "motion",
        tmp_path / "fallback.mp4",
        {},
        sprite_renderer=broken_sprite,
        kenburns_config={
            "duration": 1.0,
            "fps": 12,
            "ffmpeg_path": ffmpeg_executable,
        },
    )
    assert provider.calls == 3
    assert result.method == "internal_kenburns"
    assert len(result.errors) == 4
    assert probe_video(result.output_path, ffprobe_path=ffprobe_executable).frame_count == 12


def test_motion_fallback_rejects_existing_output_without_overwriting(tmp_path: Path) -> None:
    output = tmp_path / "existing-fallback.mp4"
    output.write_bytes(b"preserve-existing-video")
    provider = FailingVideoProvider()

    with pytest.raises(ValueError, match="already exists"):
        render_with_fallback(
            provider,
            make_image(tmp_path / "fallback-source.png"),
            "motion",
            output,
            {},
        )

    assert provider.calls == 0
    assert output.read_bytes() == b"preserve-existing-video"


def test_queue_fifteen_motion_jobs_retry_choose_and_worker(
    engine, tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    clip = make_clip(tmp_path, ffmpeg_executable, duration=1.0)
    with Session(engine) as session, session.begin():
        _episode, shots = make_episode(session, tmp_path, 15)
        jobs = [
            enqueue_motion_job(
                session,
                shot_id=shot.id,
                provider="wan_local",
                config={"ffprobe_path": ffprobe_executable},
            )
            for shot in shots
        ]
        assert len(jobs) == 15
        assert all(job.priority == "gpu" and job.status == "queued" for job in jobs)
        first_job_id = jobs[0].id
    processed = run_motion_worker(
        engine,
        providers={"wan_local": CopyVideoProvider(clip)},
        exit_when_empty=True,
        max_jobs=1,
    )
    assert processed == 1
    with Session(engine) as session, session.begin():
        first = session.get(Job, first_job_id)
        assert first is not None and first.status == "done"
        asset = session.scalar(select(Asset).where(Asset.asset_type == "video"))
        assert asset is not None
        choose_motion_asset(session, asset.id)
        assert asset.is_chosen
        failed_job = session.scalar(select(Job).where(Job.status == "queued"))
        assert failed_job is not None
        failed_job.status = "failed"
        failed_job.attempt_count = 3
        session.flush()
        retry_motion_job(session, failed_job.id)
        assert failed_job.status == "queued" and failed_job.attempt_count == 0
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 15
        assert session.scalar(select(func.count()).select_from(Asset).where(Asset.asset_type == "video")) == 1


def test_plan_subshots_rejects_unsafe_id() -> None:
    with pytest.raises(ValueError):
        plan_subshots("../s001", 5.0, 2.0)

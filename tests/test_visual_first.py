from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.exc import IntegrityError

from app.models import Asset, Episode, EpisodeReferencePin, Reference, Series, Shot
from app.db import create_session_factory
from app.providers.image.base import ImageProvider, ProviderCost, output_path, write_png_atomic
from app.qa.checker import run_asset_checks
from app.services.prompt_catalog import import_prompt_catalog, parse_prompt_catalog
from app.services.reference_mapping import auto_map_episode_references, sync_episode_reference_pins
from app.services.series import create_series
from app.services.timing import effective_shot_duration
from app.services.visual_reference import generate_reference_version
from app.services.visual_setup import prepare_visual_episode

_png_buffer = io.BytesIO()
Image.new("RGB", (2, 2), (120, 80, 40)).save(_png_buffer, format="PNG")
PNG_BYTES = _png_buffer.getvalue()
BROKEN_CRC_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


class FakeProvider(ImageProvider):
    name = "fake_flow"

    def generate(self, prompt, reference_images, config):
        assert prompt and not reference_images
        return write_png_atomic(output_path(config), PNG_BYTES)

    def cost(self, config):
        return ProviderCost(credit_amount=0, credit_type="other")


def _episode(session, tmp_path: Path) -> tuple[Series, Episode]:
    root = tmp_path / "library" / "episode"
    root.mkdir(parents=True)
    series = Series(slug="generic-series", name="Generic Series")
    episode = Episode(
        series=series,
        episode_number=1,
        slug="episode-one",
        title="Episode One",
        effective_resolution="1920x1080",
        effective_fps=30,
        effective_aspect_ratio="16:9",
        root_path=str(root),
    )
    session.add(episode)
    session.commit()
    return series, episode


def test_prompt_catalog_import_and_generated_reference_becomes_immutable_version(
    session, tmp_path: Path
) -> None:
    series = create_series(session, name="Visual Series")
    session.commit()
    entries = parse_prompt_catalog(
        "Char(main_host): character sheet prompt\nBg(bg_river_night): wide river at night"
    )
    references, created = import_prompt_catalog(session, series_id=series.id, entries=entries)
    session.commit()
    assert created == 2
    assert [item.reference_type for item in references] == ["character", "location"]
    assert references[0].aliases_json == ["main_host", "main host"]

    version = generate_reference_version(
        session,
        reference_id=references[0].id,
        provider=FakeProvider(),
        library_root=tmp_path / "library",
    )
    assert version.version == 1
    assert version.descriptor_json["provider"] == "fake_flow"
    assert (tmp_path / "library" / version.file_path).read_bytes() == PNG_BYTES


def test_prompt_catalog_rejects_duplicate_and_malformed_lines() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        parse_prompt_catalog("Char(hero): one\nChar(hero): two")
    with pytest.raises(ValueError, match="expected"):
        parse_prompt_catalog("hero = missing format")


def test_auto_mapping_and_explicit_episode_pin_sync(session, tmp_path: Path) -> None:
    series, episode = _episode(session, tmp_path)
    entries = parse_prompt_catalog(
        "Char(tao_thao): character\nBg(bg_song_xich_bich_night): location"
    )
    references, _ = import_prompt_catalog(session, series_id=series.id, entries=entries)
    unrelated = Reference(
        slug="unrelated-shared", name="Unrelated Shared", reference_type="character",
        scope="shared_across_series", generation_prompt="shared",
    )
    session.add(unrelated)
    shot = Shot(
        episode=episode,
        shot_id="s001",
        order_index=1,
        speaker="Tào Tháo",
        visual_description="Tào Tháo đứng bên sông Xích Bích trong đêm",
        characters_json=[],
        planned_duration_sec=4,
    )
    session.add(shot)
    session.commit()
    for reference in references:
        generate_reference_version(
            session,
            reference_id=reference.id,
            provider=FakeProvider(),
            library_root=tmp_path / "library",
        )
    generate_reference_version(
        session,
        reference_id=unrelated.id,
        provider=FakeProvider(),
        library_root=tmp_path / "library",
    )
    report = auto_map_episode_references(session, episode.id)
    session.commit()
    assert report.character_mapped == report.location_mapped == 1
    assert shot.characters_json == ["tao_thao"]
    assert shot.primary_character_id == "tao_thao"

    added, updated = sync_episode_reference_pins(session, episode.id)
    session.commit()
    assert (added, updated) == (2, 0)
    assert session.query(EpisodeReferencePin).filter_by(episode_id=episode.id).count() == 2
    assert not session.query(EpisodeReferencePin).filter_by(
        episode_id=episode.id, reference_id=unrelated.id
    ).count()


def test_visual_first_qa_uses_planned_duration_until_voice_arrives(session, tmp_path: Path) -> None:
    _, episode = _episode(session, tmp_path)
    image_path = Path(episode.root_path) / "images" / "chosen" / "s001.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(PNG_BYTES)
    shot = Shot(
        episode=episode, shot_id="s001", order_index=1, characters_json=[],
        planned_duration_sec=4.5,
    )
    asset = Asset(
        episode=episode, shot=shot, asset_type="image", version=1, is_chosen=True,
        file_path="images/chosen/s001.png", checksum=hashlib.sha256(PNG_BYTES).hexdigest(),
    )
    session.add_all([shot, asset])
    session.commit()
    visual_report = run_asset_checks(session, episode.id, require_audio=False, write_report=False)
    assert visual_report.passed
    assert visual_report.total_visual_timeline_sec == 4.5
    assert any(issue.code == "audio_deferred" for issue in visual_report.issues)
    assert not run_asset_checks(session, episode.id, require_audio=True, write_report=False).passed

    shot.audio_duration_sec = 6.0
    shot.head_padding_sec = 0.25
    assert effective_shot_duration(shot) == 6.25


def test_asset_checker_reports_broken_png_instead_of_crashing(session, tmp_path: Path) -> None:
    _, episode = _episode(session, tmp_path)
    image_path = Path(episode.root_path) / "images" / "chosen" / "broken.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(BROKEN_CRC_PNG)
    shot = Shot(
        episode=episode, shot_id="s001", order_index=1, characters_json=[],
        planned_duration_sec=4,
    )
    session.add(
        Asset(
            episode=episode, shot=shot, asset_type="image", version=1, is_chosen=True,
            file_path="images/chosen/broken.png",
            checksum=hashlib.sha256(BROKEN_CRC_PNG).hexdigest(),
        )
    )
    session.commit()
    report = run_asset_checks(session, episode.id, require_audio=False, write_report=False)
    assert not report.passed
    assert any(issue.code == "unreadable_metadata" for issue in report.issues)


def test_planned_duration_must_be_positive(session, tmp_path: Path) -> None:
    _, episode = _episode(session, tmp_path)
    session.add(Shot(episode=episode, shot_id="bad", order_index=1, characters_json=[], planned_duration_sec=0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_visual_setup_command_is_idempotent(engine, tmp_path: Path) -> None:
    script = tmp_path / "script.txt"
    script.write_text(
        "[SCENE: One]\n[SHOT: s001]\n[SPEAKER: Hero]\n[TEXT: Hello]\n"
        "[VISUAL: Hero at river]\n[MOTION_INTENT: static]\n",
        encoding="utf-8",
    )
    characters = tmp_path / "characters.txt"
    characters.write_text("Char(hero): generic hero sheet", encoding="utf-8")
    backgrounds = tmp_path / "backgrounds.txt"
    backgrounds.write_text("Bg(bg_river): generic river", encoding="utf-8")
    factory = create_session_factory(engine)
    kwargs = dict(
        series_name="Generic Series",
        episode_title="Generic Episode",
        episode_number=1,
        library_root=tmp_path / "library",
        script_path=script,
        character_prompts_path=characters,
        background_prompts_path=backgrounds,
        planned_duration_sec=4.0,
    )
    first = prepare_visual_episode(factory, **kwargs)
    second = prepare_visual_episode(factory, **kwargs)
    assert first.series_id == second.series_id
    assert first.episode_id == second.episode_id
    with factory() as verify:
        assert verify.query(Reference).count() == 2
        shot = verify.query(Shot).one()
        assert shot.planned_duration_sec == 4.0

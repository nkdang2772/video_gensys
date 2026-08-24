from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.parsers.common import ParseError
from app.parsers import script_csv, script_json, script_txt


def test_txt_fixture_contains_80_xich_bich_shots() -> None:
    fixture = Path(__file__).parent / "fixtures" / "xich_bich_80_fixture.txt"
    shots = script_txt.parse_file(fixture)
    assert len(shots) == 80
    assert shots[0].shot_id == "s001"
    assert shots[-1].shot_id == "s080"


def test_txt_preserves_multiline_text_and_visual() -> None:
    content = """[SCENE: 01]
[SHOT: s001]
[SPEAKER: VO]
[TEXT: Dòng thứ nhất]
Dòng thứ hai
Dòng thứ ba
[VISUAL: Toàn cảnh chiến thuyền]
Khói phủ mặt sông
[MOTION_INTENT: pan]
"""
    shot = script_txt.parse_text(content)[0]
    assert shot.text == "Dòng thứ nhất\nDòng thứ hai\nDòng thứ ba"
    assert shot.visual_description == "Toàn cảnh chiến thuyền\nKhói phủ mặt sông"


def test_txt_preserves_blank_lines_inside_multiline_fields() -> None:
    content = """[SHOT: s001]
[TEXT: First paragraph]

Second paragraph
[VISUAL: Wide shot]

Close detail
"""
    shot = script_txt.parse_text(content)[0]
    assert shot.text == "First paragraph\n\nSecond paragraph"
    assert shot.visual_description == "Wide shot\n\nClose detail"


def test_txt_rejects_content_without_shot() -> None:
    with pytest.raises(ParseError, match="before a SHOT"):
        script_txt.parse_text("[SCENE: 01]\n[TEXT: Thiếu shot]")


def test_txt_rejects_duplicate_shot_id_case_insensitively() -> None:
    with pytest.raises(ParseError, match="Duplicate shot_id"):
        script_txt.parse_text("[SHOT: S001]\n[TEXT: A]\n[SHOT: s001]\n[TEXT: B]")


def test_csv_parses_quoted_multiline_fields() -> None:
    content = 'scene,shot_id,speaker,text,visual,motion_intent\n1,s001,VO,"line 1\nline 2","view 1\nview 2",map\n'
    shot = script_csv.parse_text(content)[0]
    assert shot.text == "line 1\nline 2"
    assert shot.visual_description == "view 1\nview 2"
    assert shot.motion_intent == "map"


def test_csv_rejects_missing_shot_id() -> None:
    with pytest.raises(ParseError, match="Missing shot_id"):
        script_csv.parse_text("scene,shot_id,text\n1,,No shot\n")


def test_csv_rejects_unclosed_quoted_field() -> None:
    with pytest.raises(ParseError, match="Invalid CSV"):
        script_csv.parse_text('scene,shot_id,text\n1,s001,"unterminated\n')


def test_json_parses_wrapped_shot_list_and_multiline() -> None:
    payload = {
        "shots": [
            {
                "scene": 1,
                "shot_id": "s001",
                "speaker": "VO",
                "text": "line 1\nline 2",
                "visual_description": "river",
                "motion_intent": "generative",
            }
        ]
    }
    shot = script_json.parse_text(json.dumps(payload))[0]
    assert shot.scene == "1"
    assert shot.text == "line 1\nline 2"
    assert shot.motion_intent == "generative"


def test_json_rejects_duplicate_shot_id() -> None:
    payload = [{"shot_id": "s001"}, {"shot_id": "s001"}]
    with pytest.raises(ParseError, match="Duplicate shot_id"):
        script_json.parse_text(json.dumps(payload))


def test_json_rejects_blank_record_without_shot_id() -> None:
    with pytest.raises(ParseError, match="Missing shot_id"):
        script_json.parse_text(json.dumps([{}]))


def test_parser_rejects_unsafe_shot_id() -> None:
    with pytest.raises(ParseError, match="shot_id may only"):
        script_json.parse_text(json.dumps([{"shot_id": "../s001"}]))

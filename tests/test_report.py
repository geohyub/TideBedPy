"""Tests for TID parsing and validation helpers."""

import pytest

from output.report import parse_tid_data, parse_tid_data_cm, validate_output


def test_parse_tid_data_cm_converts_metres_to_centimetres(tmp_path):
    tid_path = tmp_path / "sample.tid"
    tid_path.write_text(
        "\n".join(
            [
                "-------------------- TideBed DB Ver.1101--PG Ver.1.0.0-----------------",
                "-------------------- TEMPORARY STATION ---------------------",
                "",
                "2026/03/01 00:00:00  1.23  0.0",
                "2026/03/01 00:01:00  -0.45  0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    data_m = parse_tid_data(str(tid_path))
    data_cm = parse_tid_data_cm(str(tid_path))

    assert data_m[0] == ("2026/03/01 00:00:00", 1.23)
    assert data_cm[0] == ("2026/03/01 00:00:00", 123.0)
    assert data_cm[1] == ("2026/03/01 00:01:00", -45.0)


def test_validate_output_sorts_mismatches_and_reports_percentage(tmp_path):
    generated = tmp_path / "generated.tid"
    reference = tmp_path / "reference.tid"

    generated.write_text(
        "\n".join(
            [
                "header",
                "",
                "2026/03/01 00:00:00  1.00  0.0",
                "2026/03/01 00:01:00  1.30  0.0",
                "2026/03/01 00:02:00  1.10  0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reference.write_text(
        "\n".join(
            [
                "header",
                "",
                "2026/03/01 00:00:00  1.00  0.0",
                "2026/03/01 00:01:00  1.00  0.0",
                "2026/03/01 00:02:00  1.08  0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_output(str(generated), str(reference), tolerance=0.05)

    assert result["matched"] == 3
    assert result["within_tolerance"] == 2
    assert result["within_tolerance_pct"] == 2 / 3 * 100
    assert result["mismatches"][0][0] == "2026/03/01 00:01:00"
    assert result["mismatches"][0][3] == pytest.approx(0.30)

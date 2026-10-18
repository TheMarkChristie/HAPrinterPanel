"""The G-code file's lines and the words for a pause at a line, without Home Assistant: python -m pytest tests -q"""
import pytest

import _load  # noqa: F401
from custom_components.printer_panel import printer as p
from custom_components.printer_panel.gcode import LineIndex


def _index(data: bytes, piece: int) -> LineIndex:
    index = LineIndex()
    for i in range(0, len(data), piece):
        index.feed(data[i:i + piece])
    return index.finish()


def test_the_lines_are_the_same_whatever_pieces_the_file_arrives_in():
    data = b"".join(b"G1 X%d Y%d\n" % (i, i) for i in range(1, 1001))
    whole = _index(data, len(data))
    assert whole.lines == 1000 and whole.size == len(data)
    for piece in (1, 7, 64, 4096):
        assert list(_index(data, piece)._ends) == list(whole._ends), piece


def test_a_position_is_the_lines_read_and_a_line_is_where_it_has_been_read():
    index = _index(b"G28\nG1 X1\nG1 X2\n", 5)  # the lines end at 4, 10 and 16
    assert [index.end_of(n) for n in (1, 2, 3)] == [4, 10, 16]
    assert [index.read_up_to(at) for at in (0, 3, 4, 9, 10, 16)] == [0, 0, 1, 1, 2, 3]


def test_windows_line_ends_and_a_last_line_without_one():
    index = _index(b"G28\r\nG1 X1\r\nM84", 3)
    assert index.lines == 3 and index.end_of(3) == index.size == 15
    assert index.read_up_to(5) == 1


def test_an_empty_file_has_no_lines():
    index = _index(b"", 4)
    assert index.lines == 0 and index.read_up_to(0) == 0
    with pytest.raises(IndexError):
        index.end_of(1)


def test_a_pause_at_a_line_says_the_line():
    assert p.message("paused_line", "en", "GTA 6 stand - Warden of Bacon", 68, None, 400018) == (
        "3D printer", "GTA 6 stand - Warden of Bacon is paused at line 400,018, as asked.")
    assert p.message("paused_line", "nb", None, 0, None, 12)[1] == "Utskriften er satt på pause ved linje 12, som du ba om."
    assert p.message("paused_line", "nb-NO", "Stand", 0, None, 400018)[1] == "Stand er satt på pause ved linje 400 018, som du ba om."

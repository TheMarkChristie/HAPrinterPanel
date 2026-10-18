"""The lines of a G-code file, with no Home Assistant in it (tested on its own). The printer's Moonraker says where it is
in the file it is printing as a byte position (virtual_sdcard.file_position, the next byte it will read): where each
line ends turns that into how many lines it has read, and a line number into the position at which it has read it."""
from __future__ import annotations

from array import array
from bisect import bisect_right


class LineIndex:
    """Where each line of one file ends (the byte after its newline), fed the file in pieces as it downloads. Half a
    million lines (a 13 MB print) is 4 MB."""

    def __init__(self) -> None:
        self._ends = array("Q")
        self._size = 0

    def feed(self, chunk: bytes) -> None:
        ends, find, base = self._ends, chunk.find, self._size
        start = 0
        while (i := find(b"\n", start)) >= 0:
            ends.append(base + i + 1)
            start = i + 1
        self._size += len(chunk)

    def finish(self) -> LineIndex:
        """The end of the file: a last line without a newline ends there."""
        if self._size and (not self._ends or self._ends[-1] != self._size):
            self._ends.append(self._size)
        return self

    @property
    def size(self) -> int:
        return self._size

    @property
    def lines(self) -> int:
        return len(self._ends)

    def read_up_to(self, position: int) -> int:
        """How many whole lines the printer has read at this position."""
        return bisect_right(self._ends, position)

    def end_of(self, line: int) -> int:
        """The position at which line (counted from 1) has been read whole."""
        if not 1 <= line <= len(self._ends):
            raise IndexError(line)
        return self._ends[line - 1]

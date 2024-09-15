import struct
from collections.abc import Sequence
from typing import List
import png

# https://web.archive.org/web/20080705155158/http://developer.apple.com/technotes/tn/tn1023.html
# https://web.archive.org/web/20150424145627/http://www.idea2ic.com/File_Formats/macpaint.pdf
# http://www.weihenstephan.org/~michaste/pagetable/mac/Inside_Macintosh.pdf
# https://en.wikipedia.org/wiki/PackBits

def chunks(lst: Sequence, n: int):
    """Yield successive n-sized chunks from lst."""
    # https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def _pack_bits(line: bytes) -> bytes:
    """
    "PackBits compresses srcBytes bytes of data starting at srcPtr and stores the compressed
    data at dstPtr. The value of srcBytes should not be greater than 127. Bytes are compressed
    when there are three or more consecutive equal bytes."
    -- http://www.weihenstephan.org/~michaste/pagetable/mac/Inside_Macintosh.pdf
    """
    packed = bytearray()
    i = 0
    while i < len(line) - 3:
        j = i
        if line[i : i + 3] == bytearray([line[i]] * 3):
            # 3+ bytes the same, compress these
            while j < len(line) and line[j] == line[i] and j - i < 127:
                j += 1
            count = j - i
            # the sign bit of the header is used to indicated whether the byte is repeated or a literal string
            # when repeated, the count is the two's complement negative value of the header
            # this must have been an efficient use of 68000 instructions or something
            header = 256 - count + 1
            byte = line[i]
            packed += struct.pack(">B", header)
            packed.append(byte)
        else:
            # literal bytes
            # find where the next 3+ byte compressible range is, stop there
            j = i + 1
            if j + 3 < len(line):
                while j - i < 127 and line[j : j + 3] != bytearray([line[j]] * 3):
                    j += 1
                    if j + 3 > len(line):
                        j = len(line)
                        break
            else:
                j = len(line)
            count = j - i
            header = count - 1  # sign bit not set
            literal_bytes = line[i : j]
            packed += struct.pack(">B", header) + literal_bytes
        i = j
    return packed


class Header:
    SIZE = 512

    def __init__(self, version: int, patterns: List[bytes], reserved: bytes, raw: bytes):
        self.version = version
        self.patterns = patterns
        self.reserved = reserved
        self.raw_str = raw

    @classmethod
    def from_file(cls, path: str):
        with open(path, 'rb') as f:
            d = f.read()
            return cls.parse(d)

    @classmethod
    def parse(cls, raw: bytes):
        version = struct.unpack("=I", raw[:4])[0]
        _patterns = struct.unpack("=" + 38*"8s", raw[4:308])
        patterns = list(_patterns)
        reserved = raw[308:]
        return cls(version, patterns, reserved, raw)

    @classmethod
    def gen_default(cls):
        version = 0
        patterns = [b'\0' for _ in range(304)]
        future = b'\0' * 204
        data = bytes()
        return cls(version, patterns, future, data)

    def pack(self) -> bytes:
        version = struct.pack(">I", self.version)
        return version + b''.join(self.patterns) + self.reserved

class MacPaintFile:
    WIDTH = 576
    HEIGHT = 720
    WHITE = 255
    BLACK = 0

    def __init__(self, header: Header, data: bytes, bitmap: List[List[int]] = None):
        self.header = header
        self.data = data
        decompressed_data = self._unpack_bits(self.data)
        self.scanlines = list(chunks(decompressed_data, self.WIDTH // 8))
        if len(self.scanlines) > self.HEIGHT:
            print("found {} junk(?) scanlines at end of file, discarding".format(len(self.scanlines) - self.HEIGHT))
            self.scanlines = self.scanlines[:self.HEIGHT]
        assert len(self.scanlines) == self.HEIGHT, "error: got {} scanlines, expected {}".format(len(self.scanlines), self.HEIGHT)
        self._bitmap: List[List[int]] = bitmap

    @classmethod
    def from_file(cls, path: str):
        header = Header.from_file(path)
        with open(path, 'rb') as f:
            filedata = f.read()
        data = filedata[Header.SIZE:]
        return cls(header, data)

    @classmethod
    def from_scanlines(cls, bitmap: List[List[int]]) -> "MacPaintFile":
        header = Header.gen_default()
        packed_bits = cls._gen_packed_data(bitmap)
        return cls(header, packed_bits, bitmap)

    def write_file(self, path: str):
        # TODO see if we can write creator code/filetype if filesystem supports it
        # this seems unlikely via python...
        with open(path, 'wb') as f:
            f.write(self.header.pack() + self.data)

    def _unpack_bits(self, scanline_data: bytes) -> bytearray:
        result = []
        i = 0
        while i < len(scanline_data):
            header = scanline_data[i]
            if header == 128:
                # ignored, next byte is another header
                i += 1
            elif header > 128:
                # twos complement -1 to -127
                # next byte repeated n times
                count = 256 - header + 1
                _byte = scanline_data[i + 1]
                decompressed = count * [_byte]
                result += decompressed
                i += 2
            else:
                # n bytes of literal uncompressed data
                count = header + 1
                _bytes = scanline_data[i+1 : i + 1 + count]
                result += list(_bytes)
                i += 1 + count
        return bytearray(result)

    @classmethod
    def _gen_packed_data(cls, bitmap: List[List[int]]) -> bytes:
        bits = bytearray()
        for _, raw_line in enumerate(bitmap):
            i = 0
            bit_line = bytearray()
            while i < len(raw_line):
                byte = 0
                for j in range(8):
                    if raw_line[i + j] == cls.BLACK:
                        byte |= 0x1 << (7 - j) # higher order bits come first left->right
                i += 8
                bit_line.append(byte)
            assert len(bit_line) == cls.WIDTH / 8
            packed_line = _pack_bits(bit_line)
            bits += packed_line
        return bits


    def to_png(self, output_path: str):
        with open(output_path, 'wb') as f:
            w = png.Writer(self.WIDTH, self.HEIGHT, greyscale=True)
            w.write(f, self.bitmap)

    @classmethod
    def from_png(cls, input_path: str) -> "MacPaintFile":
        reader = png.Reader(filename=input_path)
        width, height, rows, info = reader.read()
        if not isinstance(rows, list):
            rows = list(rows)
        rows: List[List]
        if height > cls.HEIGHT:
            rows = rows[:cls.HEIGHT]
        if height < cls.HEIGHT:
            add_rows = cls.HEIGHT - height
            for _ in range(add_rows):
                rows.append([cls.WHITE] * cls.WIDTH)
        if width > cls.WIDTH:
            rows = [row[:cls.WIDTH] for row in rows]
        if width < cls.WIDTH:
            new_rows = list()
            add_pixels = cls.WIDTH - width
            for row in rows:
                new_rows.append(row + [cls.WHITE] * add_pixels)
            rows = new_rows
        return cls.from_scanlines(rows)

    def _generate_bitmap(self):
        bitmap = []
        for i in range(len(self.scanlines)):
            scanline = self.scanlines[i]
            bitmap_line = []
            for j in range(self.WIDTH // 8):
                byte = scanline[j]
                for k in range(8):
                    mask = 0x1 << (7 - k) # higher order bits come first left->right
                    # PNG: 0 == black; MacPaint: 0 == bit/pixel not set ie white
                    bitmap_line.append(self.BLACK if (byte & mask) > 0 else self.WHITE)
            bitmap.append(bitmap_line)
        return bitmap

    @property
    def bitmap(self):
        if self._bitmap is None:
            self._bitmap = self._generate_bitmap()
        return self._bitmap


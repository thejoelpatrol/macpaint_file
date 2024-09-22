import struct
from collections.abc import Sequence
from typing import List
import sys
import png
import subprocess

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
    if len(line) > 127:
        raise RuntimeError(f"scanline is too long: {len(line)}; can only compress 127 bytes at a time, MacPaint lines should be 72 bytes")
    packed = bytearray()
    i = 0
    while i < len(line):
        # precondition: i < len(line) - 2
        if line[i : i + 3] == bytearray([line[i]] * 3):
            j = i
            # 3+ bytes the same, compress these
            while j < len(line) and line[j] == line[i] and j - i < 127:
                j += 1
            count = j - i
            # the sign bit of the header is used to indicate whether the byte is repeated or a literal string
            # when repeated, the count is the two's complement negative value of the header
            # this must have been an efficient use of 68000 instructions or something
            header = 256 - count + 1
            byte = line[i]
            packed += struct.pack(">B", header)
            packed.append(byte)
        else:
            # literal bytes
            # postcondition: j <= len(line) - 3 or  j == len(line}
            j = i + 1
            while j < len(line):
                end = min(j + 3, len(line))
                if line[j : end] == bytearray([line[j]] * 3):
                    break
                j += 1
            count = j - i
            header = count - 1  # literal bytes header is 1+n: https://en.wikipedia.org/wiki/PackBits
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
        #self._generate_bitmap()
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
        with open(path, 'wb') as f:
            f.write(self.header.pack() + self.data)

        if sys.platform == "darwin":
            PNTGMPNT = "50 4E 54 47 4D 50 4E 54 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
            command = ["xattr", "-wx", "com.apple.FinderInfo", PNTGMPNT, path]
            try:
                subprocess.check_call(command)
            except:
                print(f"warning: could not set creator code/type code with xattr; MacPaint will not be able to open {path} unless you change the creator/type codes with ResEdit or xattr")

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
        assert len(bitmap) == cls.HEIGHT, f"trying to pack {len(bitmap)} scanlines, expected {cls.HEIGHT}"
        bits = bytearray()
        for _, raw_line in enumerate(bitmap):
            i = 0
            bit_line = bytearray()
            while i < len(raw_line):
                byte = 0
                for j in range(8):
                    value = raw_line[i + j]
                    assert value in (cls.BLACK, cls.WHITE), f"got bad value for a pixel color: {value}"
                    if value == cls.BLACK:
                        byte |= 0x1 << (7 - j) # higher order bits come first left->right
                i += 8
                bit_line.append(byte)
            assert len(bit_line) == cls.WIDTH / 8, f"error in condensing bytes into bits; line is only {len(bit_line)} bytes"
            packed_line = _pack_bits(bit_line)
            bits += packed_line
        return bits

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


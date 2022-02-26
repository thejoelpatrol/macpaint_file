import struct
from collections.abc import Sequence
from typing import List
import png

# https://web.archive.org/web/20080705155158/http://developer.apple.com/technotes/tn/tn1023.html
# http://www.idea2ic.com/File_Formats/macpaint.pdf
# http://www.weihenstephan.org/~michaste/pagetable/mac/Inside_Macintosh.pdf
# https://en.wikipedia.org/wiki/PackBits

def chunks(lst: Sequence, n: int):
    """Yield successive n-sized chunks from lst."""
    # https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


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


class MacPaintFile:
    WIDTH = 576
    HEIGHT = 720

    def __init__(self, header: Header, data: bytes):
        self.header = header
        self.data = data
        decompressed_data = self._unpack_bits(self.data)
        self.scanlines = list(chunks(decompressed_data, self.WIDTH // 8))
        if len(self.scanlines) > self.HEIGHT:
            print("found {} junk scanlines at end of file, discarding".format(len(self.scanlines) - self.HEIGHT))
            self.scanlines = self.scanlines[:self.HEIGHT]
        assert len(self.scanlines) == self.HEIGHT, "error: got {} scanlines, expected {}".format(len(self.scanlines), self.HEIGHT)
        self._bitmap = None

    @classmethod
    def from_file(cls, path: str):
        header = Header.from_file(path)
        with open(path, 'rb') as f:
            filedata = f.read()
        data = filedata[Header.SIZE:]
        return cls(header, data)

    def write_file(self, path: str):
        # TODO see if we can write creator code/filetype if filesystem supports it
        pass

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

    def _pack_bits(self):
        pass

    def to_png(self, output_path: str):
        with open(output_path, 'wb') as f:
            w = png.Writer(self.WIDTH, self.HEIGHT, greyscale=True)
            w.write(f, self.bitmap)

    def _generate_bitmap(self):
        bitmap = []
        for i in range(len(self.scanlines)):
            scanline = self.scanlines[i]
            bitmap_line = []
            for j in range(self.WIDTH // 8):
                byte = scanline[j]
                for k in range(8):
                    mask = 0x1 << (7 - k)
                    bitmap_line.append( 0 if (byte & mask) > 0 else 255)
            bitmap.append(bitmap_line)
        return bitmap

    @property
    def bitmap(self):
        if self._bitmap is None:
            self._bitmap = self._generate_bitmap()
        return self._bitmap


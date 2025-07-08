from abc import ABC, abstractmethod
from typing import Sequence, List
import png
import os
import struct
from macpaint import MacPaintFile

GAMMA = 2.2

def chunks(lst: Sequence, n: int):
    """Yield successive n-sized chunks from lst."""
    # https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def dither(grey_rows: List[bytes]) -> List[bytes]:
    """
    Atkinson dithering for greyscale image
    https://beyondloom.com/blog/dither.html
    :param grey_rows: 0-255 values, one byte per pixel
    :return: 0 or 255 values only, one byte per pixel
    """
    x_y_offsets = [(1,0), (2,0), (-1,1), (0,1), (1,1), (0,2)]
    n_rows = len(grey_rows)
    errors = list()
    for _ in range(n_rows):
        errors.append([0] * len(grey_rows[0]))
    dithered = list()
    for y, row in enumerate(grey_rows):
        dithered_row = bytearray()
        for x, b in enumerate(row):
            pix = b + errors[y][x]
            col = 255 if pix > 0x80 else 0
            err = (pix - col) / 8
            for _x, _y in x_y_offsets:
                try:
                    errors[y + _y][x + _x] += err
                except IndexError:
                    continue
            if pix > 0x80:
                dithered_row.append(MacPaintFile.WHITE)
            else:
                dithered_row.append(MacPaintFile.BLACK)
        dithered.append(dithered_row)
    return dithered

def to_greyscale(color_rows: List[List[int]], alpha: bool) -> List[bytes]:
    """

    :param color_rows: 3 or 4 bytes per pixel, 8-bit RGB/A
    :param alpha: 4th alpha byte included?
    :return: 1 byte per pixel, 8-bit greyscale
    """
    if alpha:
        bytes_per_pixel = 4
        print("discarding alpha channel, sorry! re-encode without alpha for better result")
    else:
        bytes_per_pixel = 3
    greyscale_rows = list()
    for i, row in enumerate(color_rows):
        grey_row = bytearray()
        if len(row) % bytes_per_pixel != 0:
            raise RuntimeError(f"row {i} does not contain a multiple of {bytes_per_pixel} values; must be 8-bit RGB{'A' if alpha else ''}")
        for pixel in chunks(row, bytes_per_pixel):
            if alpha:
                [r, g, b, a] = pixel
            else:
                [r, g, b] = pixel
            # https://stackoverflow.com/questions/687261/converting-rgb-to-grayscale-intensity
            r_lin = pow(r / 255, GAMMA)
            g_lin = pow(g / 255, GAMMA)
            b_lin = pow(b / 255, GAMMA)
            Y = 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin
            L = (116 * pow(Y, 1/3) - 16) / 100
            if L < -5:
                raise RuntimeError(f"unexpectedly negative Luminance: {L}")
            L = max(L, 0)
            byte = round(L * 255)
            grey_row.append(byte)
        greyscale_rows.append(grey_row)
    return greyscale_rows


class ImageConverter(ABC):
    @abstractmethod
    def convert(self) -> MacPaintFile:
        raise NotImplementedError()

    @abstractmethod
    def write_image(self, path: str, macpaint_file: MacPaintFile):
        raise NotImplementedError()

    @classmethod
    def get(cls, path: str):
        filename = os.path.basename(path)
        if filename.lower().endswith(".png"):
            return PNGFile(path)
        else:
            raise NotImplementedError(f"filetype of {filename} not supported yet; only PNG so far :(")

class PNGFile(ImageConverter):
    COLORMAP = 1
    GREYSCALE = 2
    ALPHA = 4
    def __init__(self, path: str):
        reader = png.Reader(filename=path)
        self.width, self.height, self.rows, self.info = reader.read()
        self.rows = [[b for b in row] for row in self.rows]
        if reader.bitdepth == 1:
            self.rows = [[255 if b else 0 for b in row] for row in self.rows]
        elif reader.bitdepth != 8:
            raise NotImplementedError("this PNG does not use 8-bit color/grey; only 1-bit or 8-bit supported")
        # https://gitlab.com/drj11/pypng/-/blob/612d2bde70805fc85979f176410fc7fb9f3c0754/code/png.py#L1665
        # https://www.w3.org/TR/png/#6Colour-values
        colormap = bool(reader.color_type & self.COLORMAP)
        if colormap:
            raise RuntimeError("PNG uses color map; not supported, must be greyscale or RGB/RGBA")
        greyscale = not (reader.color_type & self.GREYSCALE)
        alpha = bool(reader.color_type & self.ALPHA)
        if greyscale and alpha:
            raise RuntimeError("greyscale with alpha PNG not supported; please remove alpha channel")
        if not greyscale:
            self.rows = to_greyscale(self.rows, alpha)
        if self._need_dither():
            self.rows = dither(self.rows)

        #if not isinstance(self.rows, list):
        #    self.rows = list(self.rows)
        self.rows: List[List[int]]

    def _need_dither(self):
        need_dither = False
        for row in self.rows:
            for b in row:
                if b not in (MacPaintFile.WHITE, MacPaintFile.BLACK):
                    need_dither = True
                    break
        return need_dither

    def convert(self) -> MacPaintFile:
        rows = self.rows
        if self.height > MacPaintFile.HEIGHT:
            rows = rows[:MacPaintFile.HEIGHT]
        if self.height < MacPaintFile.HEIGHT:
            add_rows = MacPaintFile.HEIGHT - height
            for _ in range(add_rows):
                rows.append([MacPaintFile.WHITE] * MacPaintFile.WIDTH)
        if self.width > MacPaintFile.WIDTH:
            rows = [row[:MacPaintFile.WIDTH] for row in rows]
        if self.width < MacPaintFile.WIDTH:
            new_rows = list()
            add_pixels = MacPaintFile.WIDTH - self.width
            for row in rows:
                new_rows.append(row + [MacPaintFile.WHITE] * add_pixels)
            rows = new_rows
        return MacPaintFile.from_scanlines(rows)

    @classmethod
    def write_image(cls, path: str, macpaint_file: MacPaintFile):
        with open(path, 'wb') as f:
            w = png.Writer(macpaint_file.WIDTH, macpaint_file.HEIGHT, greyscale=True)
            w.write(f, macpaint_file.bitmap)



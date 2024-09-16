from abc import ABC, abstractmethod
import png
from macpaint import MacPaintFile


class ImageConverterInterface(ABC):
    @abstractmethod
    def convert(self) -> MacPaintFile:
        raise NotImplementedError()

    @abstractmethod
    def write_image(self, path: str, macpaint_file: MacPaintFile):
        raise NotImplementedError()


class PNGFile(ImageConverterInterface):
    def __init__(self, path: str):
        reader = png.Reader(filename=path)
        self.width, self.height, self.rows, self.info = reader.read()
        if not isinstance(self.rows, list):
            self.rows = list(self.rows)
        self.rows: List[List]

    def convert(self) -> MacPaintFile:
        if self.height > MacPaintFile.HEIGHT:
            self.rows = self.rows[:MacPaintFile.HEIGHT]
        if self.height < MacPaintFile.HEIGHT:
            add_rows = MacPaintFile.HEIGHT - height
            for _ in range(add_rows):
                self.rows.append([MacPaintFile.WHITE] * MacPaintFile.WIDTH)
        if self.width > MacPaintFile.WIDTH:
            self.rows = [row[:MacPaintFile.WIDTH] for row in self.rows]
        if self.width < MacPaintFile.WIDTH:
            new_rows = list()
            add_pixels = MacPaintFile.WIDTH - self.width
            for row in self.rows:
                new_rows.append(row + [MacPaintFile.WHITE] * add_pixels)
            self.rows = new_rows
        return MacPaintFile.from_scanlines(self.rows)

    @classmethod
    def write_image(cls, path: str, macpaint_file: MacPaintFile):
        """
        :param bitmap: list of 0/255 values for black/white
        """
        with open(path, 'wb') as f:
            w = png.Writer(macpaint_file.WIDTH, macpaint_file.HEIGHT, greyscale=True)
            w.write(f, macpaint_file.bitmap)



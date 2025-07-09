A MacPaint file format translator. Convert MacPaint PNTG files to PNG, and vice-versa. Uses [Atkinson dithering](https://beyondloom.com/blog/dither.html) for color and grayscale input PNGs.

If you use this to rescue old MacPaint images, please submit them to www.macpaint.org!

## Setup

Python 3.x is required.

```sh
pip install -r requirements.txt
```

## Usage

```sh
./converter.py [-h] [--from-macpaint] [--to-macpaint] [--informat INFORMAT] infile outfil
```

## Type codes

When converting `--to-macpaint`, the converter will attempt to set extended attributes on the output file: a type code of `PNTG` and creator code of `MPNT`. This metadata informs classic Mac OS what type of file it is (a PaiNTinG), and how to open it (MacPaiNT).

If the image is transferred to a classic Mac over file transport that does not preserve this metadata (e.g. FTP), the type and creator codes must be manually set on the classic Mac after transferring.

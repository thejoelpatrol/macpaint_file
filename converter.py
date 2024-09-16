import argparse
from macpaint import MacPaintFile
from formats import PNGFile

def main(args):
    if args.from_macpaint:
        macpaint_file = MacPaintFile.from_file(args.infile)
        #macpaint_file.to_png(args.outfile)
        PNGFile.write_image(args.outfile, macpaint_file)
    elif args.to_macpaint:
        #macpaint_file = MacPaintFile.from_png(args.infile)
        png = PNGFile(args.infile)
        macpaint_file = png.convert()
        macpaint_file.write_file(args.outfile)
    else:
        raise RuntimeError("must specify either --from-macpaint or --to-macpaint")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-macpaint", "-m", action="store_true", help="Convert from MacPaint to PNG")
    parser.add_argument("--to-macpaint", "-p", action="store_true", help="Convert from PNG to MacPaint")
    parser.add_argument("infile", help="Input file path")
    parser.add_argument("outfile", help="Output file path")
    args = parser.parse_args()
    main(args)
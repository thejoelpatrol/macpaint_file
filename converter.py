import argparse
from macpaint import MacPaintFile

def main(args):
    macpaint_file = MacPaintFile.from_file(args.infile)
    macpaint_file.to_png(args.outfile)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", help="MacPaint file path")
    parser.add_argument("outfile", help="Output png path")
    args = parser.parse_args()
    main(args)
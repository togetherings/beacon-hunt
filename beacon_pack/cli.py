"""
beacon-pack: make BeaconHunt photo packs from Mapillary.

    beacon-pack regions
    beacon-pack build west-africa --out packs --places 1000 --zip
    beacon-pack check packs/west-africa

`build` needs your Mapillary client token in the MAPILLARY_TOKEN environment
variable. See docs/PACK_TOOL.md.
"""
import argparse
import sys

from . import geo, regions
from .build import BuildError, Options, build
from .check import check_pack
from .mapillary import Client, MapillaryError, token_from_env


def cmd_regions(_args):
    countries = geo.load_countries()
    for rid in regions.REGIONS:
        codes = regions.countries_in(rid, countries)
        print("%-20s %-26s %s" % (rid, regions.title(rid), " ".join(codes)))


def cmd_build(args):
    client = Client(token_from_env(), pause=args.pause)
    opts = Options(places=args.places, zoom=args.zoom, margin_km=args.border_km,
                   min_per_country=args.min_per_country, seed=args.seed, pano_only=args.pano_only,
                   since=args.since, countries=args.countries.split(",") if args.countries else None,
                   make_zip=args.zip)
    build(args.region, args.out, client, opts)


def cmd_check(args):
    problems, summary = check_pack(args.pack)
    if summary:
        print("%s (%s): %d places, %d of them 360°, %.1f MB" % (
            summary["title"], summary["id"], summary["places"], summary["panoramas"], summary["megabytes"]))
        print("  " + ", ".join("%s %d" % kv for kv in summary["countries"].items()))
    for p in problems:
        print("Problem: " + p)
    if problems:
        sys.exit(1)
    print("Ready to copy to a device.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="beacon-pack", description="Make BeaconHunt photo packs from Mapillary.")
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("regions", help="List the regions and their countries.")
    p.set_defaults(func=cmd_regions)

    p = sub.add_parser("build", help="Make (or carry on making) a region's pack.")
    p.add_argument("region", help="A region id, such as west-africa (see: beacon-pack regions).")
    p.add_argument("--out", default="packs", help="Folder for the pack (default: packs).")
    p.add_argument("--places", type=int, default=1000, help="How many places (default: 1000).")
    p.add_argument("--zip", action="store_true", help="Also make <region>.zip.")
    p.add_argument("--pano-only", action="store_true", help="Use only 360° photos.")
    p.add_argument("--since", type=int, help="Skip photos taken before this year.")
    p.add_argument("--countries", help="Use these countries instead of the region's, e.g. SLE,LBR.")
    p.add_argument("--border-km", type=float, default=5.0,
                   help="Skip photos this close to another country (default: 5).")
    p.add_argument("--min-per-country", type=int, default=15, help="Places every country gets at least (default: 15).")
    p.add_argument("--zoom", type=int, default=8, help="Zoom of the coverage tiles, 6 to 14 (default: 8).")
    p.add_argument("--seed", default="1", help="Change it for a different choice of places.")
    p.add_argument("--pause", type=float, default=0.1, help="Seconds between requests (default: 0.1).")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("check", help="Check a finished pack (a folder or .zip).")
    p.add_argument("pack")
    p.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (BuildError, MapillaryError) as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        sys.exit("\nStopped. Run the same command again to carry on.")


if __name__ == "__main__":
    main()

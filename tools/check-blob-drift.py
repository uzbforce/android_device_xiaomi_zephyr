#!/usr/bin/env python3
#
# SPDX-License-Identifier: Apache-2.0
#
# Compare proprietary-files.txt against an extracted firmware dump:
#
#   * missing - listed, but the dump no longer has the file (a blob the new
#     firmware dropped; extraction would fail on it)
#   * added   - in the dump but not listed, in the partitions the generator
#     scans (vendor/, odm/); these are new blobs the device likely needs
#   * unlisted - in the dump but not listed, in the partitions inherited from
#     the base (creek) list; informational, the generator does not scan these
#   * changed - same path, different content, compared against the vendor repo
#     the blobs were extracted into (that repo is the previous firmware's dump)
#
# Usage:
#   ./tools/check-blob-drift.py --dump work/root \
#       --list proprietary-files.txt \
#       --vendor ../android_vendor_xiaomi_zephyr
#
# Exits 1 when it finds drift, so it can gate a regeneration.
#
import argparse
import hashlib
import importlib.util
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
GENERATOR = os.path.join(HERE, 'gen-proprietary-files.py')


def load_generator():
    spec = importlib.util.spec_from_file_location('genpf', GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    h = hashlib.blake2b(digest_size=16)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def compare(args):
    """Return (dst, 'changed'|None) for a listed blob that exists on both sides."""
    dst, dump, vendor = args
    old = os.path.join(vendor, 'proprietary', dst)
    new = os.path.join(dump, dst)
    if os.path.getsize(old) != os.path.getsize(new):
        return dst, 'changed'
    if digest(old) != digest(new):
        return dst, 'changed'
    return dst, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', required=True,
                    help='extracted firmware root (contains vendor/, odm/, ...)')
    ap.add_argument('--list', default=os.path.join(HERE, '..', 'proprietary-files.txt'))
    ap.add_argument('--vendor', help='vendor repo to compare blob content against')
    ap.add_argument('--jobs', type=int, default=8,
                    help='content-compare workers (default 8, keep it low: the '
                         'dump is a network filesystem on most build hosts)')
    ap.add_argument('--limit', type=int, default=40,
                    help='names to print per section (default 40)')
    args = ap.parse_args()

    gen = load_generator()
    dump = args.dump
    if not os.path.isdir(os.path.join(dump, 'vendor')):
        sys.exit(f'{dump} does not look like an extracted dump (no vendor/)')

    listed = {}
    for kind, payload in gen.parse_pf(args.list):
        if kind == 'entry':
            _, dst = payload
            listed[dst] = True

    # ---- listed blobs the dump no longer has ----------------------------
    missing = sorted(d for d in listed if not gen.exists(dump, d))

    # ---- dump files the list does not cover -----------------------------
    scanned = set()
    added = []
    for part in ('odm', 'vendor'):
        for rel, _ in gen.walk_files(dump, part):
            scanned.add(rel)
            if rel == 'odm/etc/build.prop' or gen.excluded(rel):
                continue
            if rel not in listed:
                added.append(rel)
    added.sort()

    unlisted = {}
    for part in ('system', 'system_ext', 'product', 'mi_ext'):
        unlisted[part] = sum(1 for rel, _ in gen.walk_files(dump, part) if rel not in listed)

    # ---- same path, different content -----------------------------------
    changed = []
    if args.vendor:
        pairs = [(d, dump, args.vendor) for d in sorted(listed)
                 if d in scanned and os.path.isfile(os.path.join(args.vendor, 'proprietary', d))]
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for dst, verdict in pool.map(compare, pairs):
                if verdict:
                    changed.append(dst)
        changed.sort()

    def report(title, items, limit=args.limit):
        print(f'{title}: {len(items)}')
        for item in items[:limit]:
            print(f'  {item}')
        if len(items) > limit:
            print(f'  ... and {len(items) - limit} more')

    report('missing from the dump (drop these)', missing)
    report('in the dump, not listed (add these)', added)
    if args.vendor:
        report('content changed since the vendor repo was generated', changed)
    print('files present but unlisted in the inherited partitions:')
    for part, count in unlisted.items():
        print(f'  {part}: {count}')
    print('  (the generator does not scan these: they come from the base list, so a'
          '\n   count that grew is the only signal here)')

    if not missing and not added and not changed:
        print('no drift: the blob list matches the dump')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())

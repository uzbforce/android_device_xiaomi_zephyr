#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Give the stock ramoops node zones a failed boot can actually leave a log in.

The DT the stock vendor_boot carries declares its whole 2 MB reserved-memory
region as pmsg:

    ramoops_region {
        compatible = "ramoops";
        size = <0x00 0x200000>;
        pmsg-size = <0x200000>;
    };

pmsg is a userspace frontend: the kernel console and the panic dump have no
zone, so a boot that dies leaves nothing in /sys/fs/pstore and there is no
console-ramoops-0 or dmesg-ramoops-0 to read from recovery. The kernel itself
is fine - PSTORE_RAM and PSTORE_CONSOLE are both in the shipped Image
(pstore_console_write, ramoops_probe and ramoops_init_prz are in its kallsyms),
the node just never asked for those zones.

This rewrites the node in every DTB that has it, keeping the 2 MB total:

    record-size  = 0x40000   (256 KB per panic record, 4 of them)
    console-size = 0x80000   (512 KB console ring, written continuously)
    pmsg-size    = 0x80000   (512 KB, down from the full region)

It has to run after tools/gen-prebuilt-kernel.py, which copies the DTBs out of
the firmware verbatim. The DTBs are build-tree artifacts, so this is applied to
the tree in place; re-run it whenever the tree is regenerated.

    ./tools/patch-ramoops-dt.py device/xiaomi/zephyr-kernel
"""

import argparse
import os
import shutil
import subprocess
import sys

NODE = "/reserved-memory/ramoops_region"

# The node's properties are u32 in the binding (ramoops_parse_dt_size reads a
# single cell), so these stay one cell wide even though reserved-memory's own
# "size" is a 64-bit pair.
ZONES = {
    "record-size": "0x40000",
    "console-size": "0x80000",
    "pmsg-size": "0x80000",
}


def fdtget(path, prop):
    """The property as one hex cell, or None when the node does not carry it."""
    result = subprocess.run(["fdtget", "-t", "x", path, NODE, prop],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def main():
    ap = argparse.ArgumentParser(
        description="Add pstore console/record zones to the prebuilt DTBs.")
    ap.add_argument("tree", nargs="?", default="device/xiaomi/zephyr-kernel",
                    help="prebuilt kernel tree (holds dtbs/dtb/)")
    ap.add_argument("--check", action="store_true",
                    help="report what is set now, change nothing")
    args = ap.parse_args()

    dtb_dir = os.path.join(args.tree, "dtbs", "dtb")
    if not os.path.isdir(dtb_dir):
        raise SystemExit("%s does not exist - run tools/gen-prebuilt-kernel.py "
                         "first" % dtb_dir)

    names = sorted(n for n in os.listdir(dtb_dir) if n.endswith(".dtb"))
    patched = skipped = 0
    for name in names:
        path = os.path.join(dtb_dir, name)
        compatible = subprocess.run(["fdtget", "-t", "s", path, NODE, "compatible"],
                                    capture_output=True, text=True)
        if compatible.returncode != 0 or compatible.stdout.strip() != "ramoops":
            skipped += 1
            continue

        before = {prop: fdtget(path, prop) for prop in ZONES}
        if args.check:
            print("%-10s %s" % (name, before))
            patched += 1
            continue

        # Keep the stock blob outside dtb/: that directory is concatenated into
        # dtb.img, and a stray *.dtb there would be appended to the image.
        backup_dir = os.path.join(args.tree, "dtbs", ".dtb-stock")
        os.makedirs(backup_dir, exist_ok=True)
        backup = os.path.join(backup_dir, name)
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        for prop, value in ZONES.items():
            subprocess.run(["fdtput", "-t", "x", "-p", path, NODE, prop, value],
                           check=True)

        after = {prop: fdtget(path, prop) for prop in ZONES}
        for prop, value in ZONES.items():
            # fdtget -t x prints the cells without a 0x prefix.
            if after[prop] is None or int(after[prop], 16) != int(value, 16):
                raise SystemExit("%s: wrote %s=%s, read back %s"
                                 % (path, prop, value, after[prop]))
        patched += 1

    if args.check:
        print("\n%d of %d dtbs carry the node" % (patched, len(names)))
        return 0

    print("patched %d of %d dtbs (%d have no ramoops node)"
          % (patched, len(names), skipped))
    print("rebuild with: m vendor_bootimage")
    return 0


if __name__ == "__main__":
    sys.exit(main())

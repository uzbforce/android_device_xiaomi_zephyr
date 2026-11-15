#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Assemble the prebuilt kernel tree that BoardConfig.mk reads through
# ZEPHYR_PREBUILT_KERNEL_PATH (device/xiaomi/zephyr-kernel, used when
# ZEPHYR_USE_PREBUILT_KERNEL is true) out of the stock firmware.
#
#   ./tools/gen-prebuilt-kernel.py --dump work/root \
#       --firmware /path/to/zephyr_global_images_OS3.0.310.0.WBUMIXM_16.0 \
#       --out ../zephyr-kernel
#
# The stock kernel is a GKI 5.15 Image and the firmware already contains
# everything a build needs to produce a bootable pair: the Image from boot.img,
# the DTBs from dtbo.img, the dynamic modules from the vendor_dlkm and
# system_dlkm partitions, and the first-stage modules from the vendor ramdisk
# inside vendor_boot.img.  Nothing here is compiled - these are the vendor's own
# binaries, which is the point: it takes the kernel out of the first build.
#
# The layout is the one the creek tree (same SoC, same Android version) uses and
# the one BoardConfig.mk's prebuilt branch reads:
#
#   kernel                  the stock Image
#   dtbs/dtbo.img           the stock DTBO
#   dtbs/dtb/*.dtb          the vendor_boot base DTBs (27, concatenated there)
#   vendor_dlkm/*.ko        modules + modules.load + modules.blocklist
#   system_dlkm/**/*.ko     modules + modules.load (the GKI set is nested)
#   vendor_ramdisk/**       the lists the first-stage load reads (the stock
#                           ramdisk carries no .ko at all)
#
# Publish the result as its own repository and point KERNEL_PATH at it, or
# unpack it straight into device/xiaomi/zephyr-kernel.
#
# The tree is verified as it is written: the Image has to carry the arm64 magic
# and a Linux version banner, every DTBO entry has to fit the image, every
# module has to be an ELF, and every blocklist line has to be a well-formed
# "blocklist <name>" record (the build's own awk rejects anything else). The
# load lists are counted, not checked name by name: an entry may be satisfied by
# a module on another partition, and the stock recovery list even names one
# module that is in none of them.
#
# Requires python3; lz4/gzip/xz/zstd are used to expand the vendor ramdisk when
# its payload is compressed.

import argparse
import gzip
import lzma
import os
import re
import shutil
import struct
import subprocess
import sys

ARM64_IMAGE_MAGIC = 0x644D5241      # 'ARM\x64', at offset 0x38 of an arm64 Image
DTBO_MAGIC = 0xD7B7AB1E
ELF_MAGIC = b'\x7fELF'
CPIO_MAGICS = (b'070701', b'070702')

RAMDISK_TYPES = {0: 'none', 1: 'platform', 2: 'recovery', 3: 'dlkm'}

MODULE_LISTS = ('modules.load', 'modules.load.recovery', 'modules.blocklist')


def align(value, size):
    return (value + size - 1) // size * size


# ------------------------------------------------------------------ boot images


def parse_boot_image(path):
    """Parse an AOSP boot.img or vendor_boot.img header into a dict."""
    info = {'path': path, 'size': os.path.getsize(path)}
    with open(path, 'rb') as fh:
        head = fh.read(4096)
        if head[:8] == b'ANDROID!':
            _, kernel_size, ramdisk_size, _, header_size, _, _, _, \
                header_version = struct.unpack('<8s8I', head[:40])
            info.update(kind='boot', header_version=header_version,
                        page_size=4096 if header_version >= 4 else 0,
                        kernel_size=kernel_size, ramdisk_size=ramdisk_size,
                        header_size=header_size, fragments=[], name='')
            return info
        if head[:8] != b'VNDRBOOT':
            raise SystemExit('%s: neither a boot nor a vendor_boot image' % path)

        (header_version, page_size, kernel_addr, ramdisk_addr, ramdisk_size) = \
            struct.unpack('<5I', head[8:28])
        off = 28 + 2048                    # magic + 5 u32 + cmdline[2048]
        tags_addr = struct.unpack('<I', head[off:off + 4])[0]
        off += 4
        name = head[off:off + 16].split(b'\0')[0].decode()
        off += 16
        header_size = struct.unpack('<I', head[off:off + 4])[0]
        off += 4
        dtb_size = struct.unpack('<I', head[off:off + 4])[0]
        off += 4
        off += 8                           # dtb_addr (u64)

        info.update(kind='vendor_boot', header_version=header_version,
                    page_size=page_size, name=name, header_size=header_size,
                    ramdisk_size=ramdisk_size, dtb_size=dtb_size,
                    kernel_addr=kernel_addr, ramdisk_addr=ramdisk_addr,
                    tags_addr=tags_addr, fragments=[])
        ramdisk_start = align(header_size, page_size)
        if header_version < 4:
            info['fragments'].append((0, ramdisk_start, ramdisk_size, ''))
            return info

        table_size, entry_num, entry_size, bootconfig_size = \
            struct.unpack('<4I', head[off:off + 16])
        info['bootconfig_size'] = bootconfig_size
        table_off = ramdisk_start + align(ramdisk_size, page_size) + \
            align(dtb_size, page_size)
        fh.seek(table_off)
        table = fh.read(entry_num * entry_size)
        for i in range(entry_num):
            entry = table[i * entry_size:(i + 1) * entry_size]
            frag_size, frag_offset, frag_type = struct.unpack('<3I', entry[:12])
            frag_name = entry[12:44].split(b'\0')[0].decode()
            info['fragments'].append((frag_type, ramdisk_start + frag_offset,
                                      frag_size, frag_name))
        return info


def read_fragment(image, fragment):
    _, start, size, _ = fragment
    with open(image, 'rb') as fh:
        fh.seek(start)
        return fh.read(size)


# ------------------------------------------------------------------ compression


def decompress(blob, what):
    """Expand a compressed (or plain) cpio payload."""
    if blob[:2] == b'\x1f\x8b':
        return gzip.decompress(blob)
    if blob[:6] == b'\xfd7zXZ\x00':
        return lzma.decompress(blob)
    if blob[:4] in (b'\x02\x21\x4c\x18', b'\x04\x22\x4d\x18'):
        return run_filter('lz4', ['-d', '-c'], blob, what)
    if blob[:4] == b'\x28\xb5\x2f\xfd':
        return run_filter('zstd', ['-d', '-c'], blob, what)
    if blob[:6] in CPIO_MAGICS:
        return blob
    raise SystemExit('%s: unknown compression %s' % (what, blob[:4].hex()))


def run_filter(tool, args, blob, what):
    if not shutil.which(tool):
        raise SystemExit('%s: needs the %s binary to expand the payload'
                         % (what, tool))
    proc = subprocess.run([tool, *args], input=blob, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit('%s: %s failed: %s'
                         % (what, tool, proc.stderr.decode()[:200]))
    return proc.stdout


# ------------------------------------------------------------------ cpio


def cpio_entries(data):
    """Yield (name, mode, payload) for every regular file in a newc archive."""
    offset = 0
    while offset + 110 <= len(data):
        magic = data[offset:offset + 6]
        if magic not in CPIO_MAGICS:
            raise SystemExit('cpio: bad magic %r at %d' % (magic, offset))
        fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16)
                  for i in range(13)]
        mode, filesize, namesize = fields[1], fields[6], fields[11]
        name_start = offset + 110
        name = data[name_start:name_start + namesize - 1].decode()
        payload_start = align(name_start + namesize, 4)
        payload = data[payload_start:payload_start + filesize]
        offset = align(payload_start + filesize, 4)
        if name == 'TRAILER!!!':
            return
        yield name.lstrip('./'), mode, payload


def is_regular_file(mode):
    return (mode & 0o170000) == 0o100000


# ------------------------------------------------------------------ checks


def check_kernel_image(path):
    """Return the Linux version banner of an arm64 Image, or raise."""
    with open(path, 'rb') as fh:
        blob = fh.read()
    if struct.unpack('<I', blob[0x38:0x3C])[0] != ARM64_IMAGE_MAGIC:
        raise SystemExit('%s: not an arm64 Image (bad magic at 0x38)' % path)
    # The Image also carries the printk format string "Linux version %s (%s)",
    # so only a match with a version number counts.
    match = re.search(rb'Linux version \d+\.\d+[^\x00]{0,160}', blob)
    if not match:
        raise SystemExit('%s: no Linux version banner; is this a real Image?'
                         % path)
    return match.group(0).decode('utf-8', 'replace')


def check_dtbo(path):
    with open(path, 'rb') as fh:
        magic, total, header_size, entry_size, count, entries_off, page, \
            version = struct.unpack('>8I', fh.read(32))
        if magic != DTBO_MAGIC:
            raise SystemExit('%s: not a dtbo image' % path)
        # The header's total is the content size; the partition pads the file.
        if total > os.path.getsize(path):
            raise SystemExit('%s: header says %d bytes, file is only %d'
                             % (path, total, os.path.getsize(path)))
        fh.seek(entries_off)
        table = fh.read(count * entry_size)
        blob_size = total
    entries = []
    for i in range(count):
        size, offset, id_, rev = struct.unpack('>4I',
                                               table[i * entry_size:
                                                     i * entry_size + 16])
        if offset + size > blob_size:
            raise SystemExit('%s: dtb %d runs past the end of the image' % (path, i))
        entries.append((size, offset, id_, rev))
    return entries


def extract_vendor_boot_dtbs(firmware, out):
    """Split the base DTBs out of the stock vendor_boot dtb section."""
    image = os.path.join(firmware, 'images', 'vendor_boot.img')
    if not os.path.exists(image):
        return 'no vendor_boot.img in the firmware package'
    info = parse_boot_image(image)
    if info['kind'] != 'vendor_boot':
        return 'vendor_boot.img is not a vendor_boot image'
    if not info.get('dtb_size'):
        return 'vendor_boot.img carries no dtb section'
    page = info['page_size']
    start = align(info['header_size'], page) + align(info['ramdisk_size'], page)
    with open(image, 'rb') as fh:
        fh.seek(start)
        blob = fh.read(info['dtb_size'])
    dtb_dir = os.path.join(out, 'dtbs', 'dtb')
    shutil.rmtree(dtb_dir, ignore_errors=True)
    shutil.rmtree(os.path.join(out, 'dtbs', '.dtb-stock'), ignore_errors=True)
    os.makedirs(dtb_dir)
    offset = 0
    count = 0
    while offset + 8 <= len(blob):
        magic, total = struct.unpack('>II', blob[offset:offset + 8])
        if magic != 0xd00dfeed:
            raise SystemExit('%s: dtb %d has bad magic %#x at offset %d' % (image, count, magic, offset))
        if total < 8 or offset + total > len(blob):
            raise SystemExit('%s: dtb %d runs past the dtb section' % (image, count))
        with open(os.path.join(dtb_dir, '%02d.dtb' % count), 'wb') as fh:
            fh.write(blob[offset:offset + total])
        offset += total
        count += 1
    if offset != len(blob):
        raise SystemExit('%s: %d trailing bytes after the last dtb' % (image, len(blob) - offset))
    if not count:
        raise SystemExit('%s: the dtb section is empty' % image)
    return count


def module_tree(root):
    """Return (module paths relative to root, {list name: entries}).

    modules.blocklist records are "blocklist <name>" lines; the entry is kept
    as the name, and anything else is rejected the way the build's awk rejects
    it (libmodprobe would refuse to parse it).
    """
    modules = []
    for base, _, files in os.walk(root):
        for name in sorted(files):
            if name.endswith('.ko'):
                modules.append(os.path.relpath(os.path.join(base, name), root))
    lists = {}
    for list_name in MODULE_LISTS:
        path = os.path.join(root, list_name)
        if not os.path.exists(path):
            continue
        entries = []
        for number, line in enumerate(open(path), 1):
            entry = line.strip()
            if not entry or entry.startswith('#'):
                continue
            if list_name == 'modules.blocklist':
                fields = entry.split()
                if len(fields) != 2 or fields[0] != 'blocklist':
                    raise SystemExit('%s:%d: not a "blocklist <name>" line: %r'
                                     % (path, number, entry))
                entry = fields[1]
            entries.append(entry)
        lists[list_name] = entries
    return sorted(modules), lists


def check_module_tree(root, what):
    """Verify that the .ko files are real and the lists parse."""
    modules, lists = module_tree(root)
    for rel in modules:
        with open(os.path.join(root, rel), 'rb') as fh:
            if fh.read(4) != ELF_MAGIC:
                raise SystemExit('%s: %s is not an ELF object' % (what, rel))
    return modules, lists


def describe(lists):
    """Summarise a module tree's lists in one line."""
    load = len(lists.get('modules.load', []))
    block = len(lists.get('modules.blocklist', []))
    recovery = len(lists.get('modules.load.recovery', []))
    text = 'modules.load: %d entries, %d blocklisted' % (load, block)
    if recovery:
        text += ', recovery load list: %d' % recovery
    return text


# ------------------------------------------------------------------ assembly


def copy_module_tree(src_root, dst_root, what):
    """Copy a module tree, keeping the paths that modules.load refers to."""
    os.makedirs(dst_root, exist_ok=True)
    modules, _ = module_tree(src_root)
    for rel in modules + [name for name in MODULE_LISTS
                          if os.path.exists(os.path.join(src_root, name))]:
        target = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(src_root, rel), target)

    # The stock modules.load of this device lists 46 modules twice; loading a
    # module that is already loaded fails, so the copy is de-duplicated with the
    # original order kept.
    path = os.path.join(dst_root, 'modules.load')
    if os.path.exists(path):
        entries = [l.strip() for l in open(path) if l.strip()]
        unique = list(dict.fromkeys(entries))
        if len(unique) != len(entries):
            with open(path, 'w') as fh:
                fh.write('\n'.join(unique) + '\n')
            print('  %-13s modules.load: %d entries, %d duplicates removed'
                  % (what, len(entries), len(entries) - len(unique)))
    return module_tree(dst_root)


def find_modules_root(dump, partition):
    """Find the directory that modules.load is relative to."""
    partition_root = os.path.join(dump, partition)
    if not os.path.isdir(partition_root):
        return None
    candidates = []
    for base, _, files in os.walk(partition_root):
        if 'modules.load' in files:
            candidates.append(base)
    if candidates:
        return sorted(candidates, key=len)[0]
    for base, _, files in os.walk(partition_root):
        if any(f.endswith('.ko') for f in files):
            return base
    return None


def extract_vendor_ramdisk(firmware, out):
    """Pull the first-stage modules out of the vendor ramdisk."""
    image = os.path.join(firmware, 'images', 'vendor_boot.img')
    if not os.path.exists(image):
        return 'no vendor_boot.img in the firmware package'
    info = parse_boot_image(image)
    if not info['fragments']:
        return 'vendor_boot.img carries no ramdisks'
    dst = os.path.join(out, 'vendor_ramdisk')
    os.makedirs(dst, exist_ok=True)
    total = 0
    for fragment in info['fragments']:
        frag_type, _, _, frag_name = fragment
        blob = read_fragment(image, fragment)
        entries = list(cpio_entries(decompress(blob, 'vendor_boot.img')))
        count = 0
        for name, mode, payload in entries:
            if not is_regular_file(mode):
                continue
            rel = name.split('lib/modules/')[-1]
            if not (rel.endswith('.ko') or os.path.basename(rel) in MODULE_LISTS):
                continue
            target = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as fh:
                fh.write(payload)
            count += 1
        print('  vendor_ramdisk fragment %-12s type=%-8s %6.1f MB, %d files'
              % (frag_name or '(unnamed)',
                 RAMDISK_TYPES.get(frag_type, frag_type), len(blob) / 1e6, count))
        total += count
    if not total:
        return 'the vendor ramdisk holds no modules'
    return None


def main():
    ap = argparse.ArgumentParser(
        description='Assemble the prebuilt kernel tree from the stock firmware.')
    ap.add_argument('--dump', default='work/root',
                    help='extracted firmware tree (holds vendor_dlkm/ and '
                         'system_dlkm/)')
    ap.add_argument('--firmware', required=True,
                    help='firmware package directory (holds images/)')
    ap.add_argument('--out', default='device/xiaomi/zephyr-kernel',
                    help='where to write the tree')
    ap.add_argument('--kernel', default=None,
                    help='stock Image to use (default: work/boot/boot.kernel '
                         'next to --dump, else images/boot.img)')
    args = ap.parse_args()

    dump = args.dump
    firmware = args.firmware
    if not os.path.isdir(dump):
        raise SystemExit('%s does not exist' % dump)
    if not os.path.isdir(os.path.join(firmware, 'images')):
        raise SystemExit('%s/images does not exist' % firmware)
    if os.path.exists(args.out) and os.listdir(args.out):
        print('warning: %s is not empty, files are overwritten' % args.out)
    os.makedirs(os.path.join(args.out, 'dtbs'), exist_ok=True)

    # ---- the kernel
    kernel_src = args.kernel
    if not kernel_src:
        candidate = os.path.join(os.path.dirname(os.path.abspath(dump.rstrip('/'))),
                                 'boot', 'boot.kernel')
        if os.path.exists(candidate):
            kernel_src = candidate
    if kernel_src:
        shutil.copy2(kernel_src, os.path.join(args.out, 'kernel'))
        origin = kernel_src
    else:
        boot = os.path.join(firmware, 'images', 'boot.img')
        info = parse_boot_image(boot)
        with open(boot, 'rb') as fh:
            fh.seek(align(info['header_size'], 4096))
            data = fh.read(info['kernel_size'])
        with open(os.path.join(args.out, 'kernel'), 'wb') as fh:
            fh.write(data)
        origin = boot
    banner = check_kernel_image(os.path.join(args.out, 'kernel'))
    print('  kernel        <- %s' % origin)
    print('                  %s (%d bytes)' % (banner, os.path.getsize(
        os.path.join(args.out, 'kernel'))))

    # ---- dtbo
    dtbo = os.path.join(firmware, 'images', 'dtbo.img')
    if not os.path.exists(dtbo):
        raise SystemExit('%s: missing' % dtbo)
    shutil.copy2(dtbo, os.path.join(args.out, 'dtbs', 'dtbo.img'))
    entries = check_dtbo(os.path.join(args.out, 'dtbs', 'dtbo.img'))
    ids = sorted({e[2] for e in entries})
    print('  dtbs/dtbo.img <- %s (%d dtbs, ids %s, %d bytes of dtbs) '
          '[%d bytes of partition]'
          % (dtbo, len(entries), ','.join(str(i) for i in ids),
             sum(e[0] for e in entries), os.path.getsize(dtbo)))

    base_dtbs = extract_vendor_boot_dtbs(firmware, args.out)
    if isinstance(base_dtbs, str):
        print('  dtbs/dtb/     ! %s' % base_dtbs)
    else:
        print('  dtbs/dtb/     <- vendor_boot.img (%d base dtbs)' % base_dtbs)

    # ---- the dynamic partitions
    for partition in ('vendor_dlkm', 'system_dlkm'):
        src = find_modules_root(dump, partition)
        if not src:
            print('  %-13s ! nothing module-like under %s/%s'
                  % (partition, dump, partition))
            continue
        copy_module_tree(src, os.path.join(args.out, partition), partition)
        modules, lists = check_module_tree(
            os.path.join(args.out, partition), partition)
        print('  %-13s <- %s' % (partition, os.path.relpath(src, dump)))
        print('                  %d modules (%d nested), %s'
              % (len(modules), len([m for m in modules if '/' in m]),
                 describe(lists)))

    # ---- first-stage modules
    error = extract_vendor_ramdisk(firmware, args.out)
    if error:
        print('  vendor_ramdisk ! %s' % error)
    else:
        modules, lists = check_module_tree(
            os.path.join(args.out, 'vendor_ramdisk'), 'vendor_ramdisk')
        present = set()
        for partition in ('vendor_dlkm', 'system_dlkm', 'vendor_ramdisk'):
            for _, _, files in os.walk(os.path.join(args.out, partition)):
                present.update(f for f in files if f.endswith('.ko'))
        load = lists.get('modules.load', [])
        built_in = [name for name in load if name not in present]
        print('                  %d modules, %s'
              % (len(modules), describe(lists)))
        print('                  %d of the first-stage names have a .ko here, '
              '%d are built into the Image'
              % (len(load) - len(built_in), len(built_in)))

    print('\n%s assembled.' % args.out)
    print('Build it with ZEPHYR_USE_PREBUILT_KERNEL := true; see README, "Kernel".')
    return 0


if __name__ == '__main__':
    sys.exit(main())

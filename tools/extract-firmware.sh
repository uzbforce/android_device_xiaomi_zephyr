#!/usr/bin/env bash
#
# Unpack a Xiaomi HyperOS fastboot package into an inspectable tree.
#
#   ./tools/extract-firmware.sh /path/to/zephyr_global_images_OS3.0.310.0.WBUMIXM_16.0 [workdir]
#
# Produces, under workdir (default: ./work):
#   super.raw.img        unsparsed super
#   parts/*.img          individual logical partitions (odm_a, vendor_a, ...)
#   root/<name>/         extracted filesystem for every partition, addressed by
#                        device path (root/system/bin/... is /system/bin/...)
#   root/<name>_root/    for a system-as-root partition, the image's own root:
#                        the stock system.img is built system-as-root, so its
#                        /init, /etc and /bin are symlinks into an inner
#                        /system directory. That inner directory is what lands
#                        on /system, so it is promoted to root/system and the
#                        image root is kept as root/system_root - the same
#                        layout extract_utils' move_sar_system_paths produces
#   dtbo/*.dtb + dts/    every DTB from dtbo.img, and its decompiled DTS
#   boot/*.kernel        kernel Image from boot.img, ramdisks from init_boot/recovery
#
# Requirements: simg2img, lpunpack (android-sdk-libsparse-utils / lpunpack), python3,
#   fsck.erofs (erofs-utils) and dtc. On a machine without root, build the last two:
#     git clone --depth 1 https://github.com/erofs/erofs-utils && cd erofs-utils
#       && ./autogen.sh && ./configure --disable-fuse --without-selinux && make -j && make install
#     git clone --depth 1 https://github.com/dgibson/dtc && cd dtc && make NO_PYTHON=1 NO_YAML=1 dtc fdtdump
#
set -euo pipefail

FW="${1:-}"
WORK="${2:-work}"

if [[ -z "$FW" || ! -d "$FW/images" ]]; then
    echo "usage: $0 <firmware-dir containing images/> [workdir]" >&2
    exit 1
fi

need() { command -v "$1" >/dev/null || { echo "missing tool: $1" >&2; exit 1; }; }
need simg2img
need lpunpack
need python3
need fsck.erofs
need dtc

IMG="$FW/images"
mkdir -p "$WORK"/{parts,root,dtbo,dts,boot}

# Reuse the unpacked partitions when they are already there: unsparsing and
# lpunpack move ~13 GB and nothing below this point depends on them being fresh
# unless super.img itself changed.
if [[ -s "$WORK/super.raw.img" && -s "$WORK/partitions.txt" && -n "$(ls -A "$WORK/parts" 2>/dev/null)" ]]; then
    echo "==> reusing super.raw.img and parts/ (delete them to redo)"
else
    echo "==> unsparsing super.img"
    simg2img "$IMG/super.img" "$WORK/super.raw.img"

    echo "==> unpacking logical partitions"
    lpdump "$WORK/super.raw.img" | grep -E '^\s+Name:' | sed 's/.*Name: //' | sort -u > "$WORK/partitions.txt"
    lpunpack "$WORK/super.raw.img" "$WORK/parts"
fi

echo "==> extracting EROFS partitions"
while read -r part; do
    src="$WORK/parts/$part.img"
    [[ -s "$src" ]] || continue
    name="${part%_a}"
    # erofs magic at offset 1024: e2 e1 f5 e0
    if [[ "$(xxd -s 1024 -l 4 -p "$src")" == "e2e1f5e0" ]]; then
        echo "    $part -> root/$name"
        rm -rf "$WORK/root/$name"
        fsck.erofs --extract="$WORK/root/$name" "$src" >/dev/null 2>&1 || \
            echo "    !! fsck.erofs reported errors on $part (usually harmless for a dump)"
        # system-as-root: the image root is symlinks into /system, so the inner
        # directory is the filesystem that becomes /system
        if [[ -L "$WORK/root/$name/bin" && -d "$WORK/root/$name/system/bin" ]]; then
            echo "    $part is system-as-root, promoting its inner /system"
            rm -rf "$WORK/root/${name}_root"
            mv "$WORK/root/$name" "$WORK/root/${name}_root"
            mv "$WORK/root/${name}_root/system" "$WORK/root/$name"
        fi
    else
        echo "    $part is not EROFS, skipping"
    fi
done < "$WORK/partitions.txt"

echo "==> splitting dtbo.img"
python3 - "$IMG/dtbo.img" "$WORK/dtbo" <<'PY'
import struct, sys, os
src, out = sys.argv[1], sys.argv[2]
d = open(src, 'rb').read()
magic, total, hdr, esz, count, off, page, ver = struct.unpack('>8I', d[:32])
if magic != 0xd7b7ab1e:
    sys.exit('not a dtbo image')
for i in range(count):
    e = d[hdr + i * esz: hdr + (i + 1) * esz]
    size, o, id_, rev = struct.unpack('>4I', e[:16])
    open(os.path.join(out, f'{i:03d}_id{id_}_rev{rev}.dtb'), 'wb').write(d[o:o + size])
print(f'    {count} dtbs')
PY

echo "==> decompiling dtbs"
for f in "$WORK"/dtbo/*.dtb; do
    dtc -q -I dtb -O dts "$f" -o "$WORK/dts/$(basename "${f%.dtb}").dts" 2>/dev/null || true
done

echo "==> splitting boot images"
python3 - "$IMG" "$WORK/boot" <<'PY'
import struct, os, sys
img, out = sys.argv[1], sys.argv[2]
for name in ('boot.img', 'init_boot.img', 'recovery.img'):
    p = os.path.join(img, name)
    if not os.path.exists(p):
        continue
    d = open(p, 'rb').read()
    if d[:8] != b'ANDROID!':
        continue
    ks, rs = struct.unpack('<2I', d[8:16])
    page = 4096                      # v3/v4 header page size
    base = name.replace('.img', '')
    if ks:
        open(os.path.join(out, base + '.kernel'), 'wb').write(d[page:page + ks])
    if rs:
        off = page + ((ks + page - 1) // page) * page
        open(os.path.join(out, base + '.ramdisk.lz4'), 'wb').write(d[off:off + rs])
    print(f'    {base}: kernel={ks} ramdisk={rs}')
PY

echo
echo "done."
echo "  partitions : $WORK/parts"
echo "  filesystems: $WORK/root"
echo "  device trees: $WORK/dts"
echo "  boot images : $WORK/boot"

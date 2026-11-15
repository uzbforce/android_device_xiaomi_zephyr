#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Produce the uapi header set that BoardConfig.mk hands to the HALs through
# TARGET_BOARD_KERNEL_HEADERS.
#
#   tools/gen-kernel-headers.sh [--kernel <dir>] [--out <dir>]
#
# Defaults: kernel/xiaomi/zephyr of the checkout and the prebuilt kernel tree
# (device/xiaomi/zephyr-kernel, or $ZEPHYR_PREBUILT_KERNEL_PATH). Run it from
# the root of the Android tree, after `source build/envsetup.sh` is not needed;
# ANDROID_BUILD_TOP is honoured when set.
#
# The exported set has to be sanitized the way LineageOS sanitizes the headers
# of an inline build: `headers_install` writes an asm-generic/signal.h that
# redefines struct sigaction, and since TARGET_BOARD_KERNEL_HEADERS is added as
# an -isystem for every module, that collides with bionic's own definition in
# every file that includes a libc header ("redefinition of 'sigaction'"). The
# kernel's sched_param guard (patches/kernel/xiaomi/zephyr in the patches repo)
# has to be in the source before this runs, or the exported
# linux/sched/types.h redefines struct sched_param and libipanat fails the same
# way.

set -eu

top="${ANDROID_BUILD_TOP:-$PWD}"
kernel="$top/kernel/xiaomi/zephyr"
out="${ZEPHYR_PREBUILT_KERNEL_PATH:-$top/device/xiaomi/zephyr-kernel}"

while [ $# -gt 0 ]; do
    case "$1" in
        --kernel) kernel="$2"; shift 2 ;;
        --out) out="$2"; shift 2 ;;
        -h|--help) sed -n '3,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

[ -f "$kernel/Makefile" ] || { echo "$kernel is not a kernel tree" >&2; exit 1; }
[ -d "$top/bionic/libc/kernel/tools" ] || { echo "$top is not an Android tree" >&2; exit 1; }

tmp="$top/out-hdr"
dest="$out/kernel-headers"

echo "headers_install: $kernel -> $tmp"
rm -rf "$tmp"
mkdir -p "$tmp"
make -C "$kernel" O="$tmp" ARCH=arm64 INSTALL_HDR_PATH="$tmp/usr" headers_install

# clean_header.py only rewrites files it is given as absolute paths.
echo "sanitizing asm*/signal.h against bionic"
python3 "$top/bionic/libc/kernel/tools/clean_header.py" -u \
    "$tmp/usr/include/asm/signal.h" \
    "$tmp/usr/include/asm-generic/signal.h"

if grep -q 'struct sigaction' "$tmp/usr/include/asm-generic/signal.h"; then
    echo "asm-generic/signal.h still defines struct sigaction; bionic will clash" >&2
    exit 1
fi

echo "installing into $dest"
rm -rf "$dest"
mkdir -p "$dest"
cp -a "$tmp/usr/include/." "$dest/"
rm -rf "$tmp"

echo "done: $(find "$dest" -type f | wc -l) headers"

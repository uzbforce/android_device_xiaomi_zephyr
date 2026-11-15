#!/usr/bin/env python3
#
# Generate proprietary-files.txt for zephyr (Redmi Note 17 4G / p19a) from an
# extracted stock firmware dump.
#
#   ./tools/gen-proprietary-files.py --dump work/root \
#       --base work/src/creek_proprietary-files.txt \
#       --out proprietary-files.txt
#
# Strategy:
#   * start from the creek (Redmi 15 4G) list, which covers the shared
#     mivendor_sm6225 stack, and keep only entries that actually exist here
#   * add every file under odm/ (per-device partition, small)
#   * add every vendor/ file that is a blob, minus things the build system
#     generates itself (build.prop, fs_config_*, the main VINTF manifest,
#     rootdir init scripts, vendor sepolicy)
#   * kernel modules are NOT listed: they come from the kernel repo
#     (MiCode/Xiaomi_Kernel_OpenSource, branch zephyr-w-oss) into vendor_dlkm /
#     system_dlkm
#
# Symlinks are folded into the file they point at using extract_utils'
# `|SYMLINK=name` syntax.
#
import argparse
import os
import re
import sys

PARTITIONS = ('vendor', 'odm', 'system_ext', 'product', 'system')

# Paths that must not be shipped as blobs: the device tree or the build system
# produces them.
#
# The clearkey DRM service is the platform's: frameworks/av/drm/mediadrm/plugins/
# clearkey/service.mk adds android.hardware.drm-service.clearkey to
# PRODUCT_PACKAGES, and that module installs the binary, its init rc and a VINTF
# fragment into vendor/. Shipping the stock copies puts two installs on the same
# three paths, and the two fragment modules define the same make target -
# kati stops with "MODULE.TARGET.ETC.android.hardware.drm-service.clearkey.xml
# already defined by frameworks/av/drm/mediadrm/plugins/clearkey/aidl". The
# platform copy is also the one to keep: it declares android.hardware.drm AIDL
# version 2, where the stock fragment declares version 1.
VENDOR_EXCLUDES = (
    'vendor/build.prop',
    'vendor/etc/fs_config_dirs',
    'vendor/etc/fs_config_files',
    'vendor/etc/vintf/manifest.xml',
    # The build generates the compatibility matrix from the platform's own
    # matrix fragments; shipping the stock one puts two installs on this path.
    'vendor/etc/vintf/compatibility_matrix.xml',
    'vendor/bin/hw/android.hardware.drm-service.clearkey',
    'vendor/etc/init/android.hardware.drm-service.clearkey.rc',
    'vendor/etc/vintf/manifest/android.hardware.drm-service.clearkey.xml',
    # vendor/qcom/opensource/vibrator builds the qcom vibrator HAL - the service
    # binary, its init rc and the implementation library - and device.mk installs
    # it, because nothing inherits vibrator-vendor-product.mk, so the module has
    # to be named there. The stock copies install onto those same three paths and
    # PRODUCT_COPY_FILES lands after the module, so the stock pieces won: the
    # image ended up with the stock binary (20232 bytes, build id 112055db...,
    # the same one the blob directory holds) instead of the tree's own (19160),
    # and with the stock vendor.qti.hardware.vibrator.impl.so (53776, where the
    # tree builds 27096). That stock service does not survive this platform: its
    # library logs "not a qcom/qti haptics device", its open of
    # /sys/class/leds/vibrator/activate fails with EACCES, and the daemon aborts
    # with "Check failed: status == STATUS_OK" and restarts forever. The
    # service, its rc and its library have to come from the same build.
    'vendor/bin/hw/vendor.qti.hardware.vibrator.service',
    'vendor/etc/init/vendor.qti.hardware.vibrator.service.rc',
    'vendor/lib64/vendor.qti.hardware.vibrator.impl.so',
    # Android 16 builds its own all-versions audio HAL service and the device
    # tree installs it together with android.hardware.audio@7.1-impl. The stock
    # Android 13 service_64 rc carries `override`, sorts after the tree's rc
    # (android.hardware.audio.service.rc), and so replaced the tree service with
    # a binary that segfaults in BnHwDevice::_hidl_setParameters on the first
    # setParameters call. audioserver then dies on every start, AudioService
    # blocks in AudioSystem.setLowRamDevice during its constructor, and the
    # system_server watchdog kills it after 67 s - a permanent restart loop once
    # the setup wizard starts touching audio. Keep the stock binary and its rc
    # out of the image so the tree service (7.1 first, 7.0 fallback) runs.
    'vendor/bin/hw/android.hardware.audio.service_64',
    'vendor/etc/init/android.hardware.audio.service_64.rc',
    # frameworks/native builds vndservicemanager for this release, and the
    # stock prebuilt implements IServiceManager against a different libbinder
    # than the tree installs, so it aborts in ServiceManager::listServices and
    # leaves /dev/vndbinder without a context manager. The binary and its rc
    # stay out; the product packages the module instead.
    'vendor/bin/vndservicemanager',
    'vendor/etc/init/vndservicemanager.rc',
)
VENDOR_EXCLUDE_PREFIXES = (
    'vendor/etc/init/hw/',
    'vendor/etc/selinux/',
    'vendor/odm_dlkm/',
    # RRO APKs: extract_utils has no package rule for overlay/; the tree ships
    # its own overlays instead.
    'vendor/overlay/',
)

# VINTF fragments the ROM itself generates, for HALs it builds from source -
# the qcom-caf platform trees (memtrack, audio primary-hal), Lineage's qcom HALs
# (power, vibrator, healthd-ext) and AOSP's HALs (atrace, boot, cas, ir, sensors
# multihal, usb gadget). The stock vendor image ships a fragment with the same
# filename, and both arrive as soong modules, so the two define one make target
# and kati stops with "MODULE.TARGET.ETC.<name> already defined by <platform
# tree>". Whichever side the ROM would install, the fragment has to come from
# the platform - its fragment modules are part of the product and cannot be
# removed. Each of these was confirmed against the generated ninja: the platform
# tree produces them.
#
# The three display fragments that used to be in this list are not here any
# more. They came from hardware/qcom-caf/sm6225/display, whose composer,
# allocator and mapper HALs cannot be built against this kernel (its SDE/DPU
# code includes the techpack display headers, see the display section in
# device.mk), so those HALs - and their fragments - come from the stock vendor
# image again. memtrack is still platform-built: it lives in
# hardware/qcom-caf/common, not in the sm6225 tree.
PLATFORM_FRAGMENT_EXCLUDES = (
    'vendor/etc/vintf/manifest/android.hardware.atrace@1.0-service.xml',
    'vendor/etc/vintf/manifest/android.hardware.boot@1.2.xml',
    'vendor/etc/vintf/manifest/android.hardware.cas@1.2-service.xml',
    'vendor/etc/vintf/manifest/android.hardware.health-service.qti.xml',
    'vendor/etc/vintf/manifest/android.hardware.ir-service.example.xml',
    'vendor/etc/vintf/manifest/android.hardware.sensors@2.1-multihal.xml',
    'vendor/etc/vintf/manifest/android.hardware.usb.gadget@1.1-service.xml',
    'vendor/etc/vintf/manifest/android.hardware.wifi.hostapd.xml',
    'vendor/etc/vintf/manifest/android.hardware.wifi.supplicant.xml',
    'vendor/etc/vintf/manifest/manifest_non_qmaa.xml',
    'vendor/etc/vintf/manifest/memtrack_qti.xml',
    'vendor/etc/vintf/manifest/power.xml',
    'vendor/etc/vintf/manifest/vendor.qti.hardware.vibrator.service.xml',
)


def excluded(dst):
    return (
        dst in VENDOR_EXCLUDES
        or dst in PLATFORM_FRAGMENT_EXCLUDES
        or any(dst.startswith(p) for p in VENDOR_EXCLUDE_PREFIXES)
    )


# extract_utils reads `|` as a hash pin and `;` as an argument, so `|SYMLINK=`
# (which an earlier revision of this script wrote) was silently parsed as a
# pinned hash instead of a symlink. Strip it while inheriting from such a list.
LEGACY_SYMLINK_ARG = re.compile(r'\|SYMLINK=[^|]*')

# Header lines this generator writes itself. Regenerating from an existing
# proprietary-files.txt (rather than from the creek seed) would otherwise copy
# them into the inherited section and emit them a second time.
GENERATED_SCAFFOLD = (
    '# Blobs extracted from zephyr ',
    '# Generated by tools/gen-proprietary-files.py',
    '# Sections above "zephyr additions" are inherited from the creek list.',
)

ADDITIONS_MARKER = '# Zephyr (p19a) additions'


def is_scaffold(text):
    return any(text.startswith(prefix) for prefix in GENERATED_SCAFFOLD)


def norm(line):
    return line.rstrip('\r\n')


def parse_pf(path):
    """Return list of (kind, text) where kind is 'comment' or 'entry'."""
    out = []
    for raw in open(path, encoding='utf-8', errors='replace'):
        if raw.lstrip().startswith('# All blobs below are extracted from'):
            continue
        line = norm(raw).strip()
        if not line:
            out.append(('blank', ''))
            continue
        if line.startswith('#'):
            out.append(('comment', line))
            continue
        line = LEGACY_SYMLINK_ARG.sub('', line)
        # strip optional '-' prefix and hash/fixup suffix for existence check
        dst = line[1:] if line.startswith('-') else line
        dst = dst.split(';')[0].split('|')[0].strip()
        out.append(('entry', (line, dst)))
    return out


def exists(dump, dst):
    return os.path.isfile(os.path.join(dump, dst))


def walk_files(dump, partition):
    base = os.path.join(dump, partition)
    if not os.path.isdir(base):
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            # Absolute or dangling symlinks are created on-device (by init or
            # ueventd) or point into another partition; they are not blobs.
            # Relative symlinks are folded into their target further down.
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, dump)
            yield rel, full


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', required=True, help='extracted firmware root (contains vendor/, odm/, ...)')
    ap.add_argument('--base', help='reference proprietary-files.txt to inherit curated sections from')
    ap.add_argument('--out', default='proprietary-files.txt')
    ap.add_argument('--firmware-label', default='OS3.0.310.0.WBUMIXM',
                    help='firmware the dump came from, written into the header')
    args = ap.parse_args()

    dump = args.dump
    if not os.path.isdir(os.path.join(dump, 'vendor')):
        sys.exit(f'{dump} does not look like an extracted dump (no vendor/)')

    # ---- collect symlinks, keyed by the file they point at --------------
    #
    # extract_utils declares a link on the *target's* entry, as
    # `dst;SYMLINK=<link path>` - a bare name when the link sits next to the
    # target, otherwise a partition-relative path. So the link's own directory
    # matters, not just its name.
    symlinks = {}
    dangling = []
    external = []
    for part in ('vendor', 'odm'):
        base = os.path.join(dump, part)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            for name in list(dirnames) + list(filenames):
                full = os.path.join(dirpath, name)
                if not os.path.islink(full):
                    continue
                link_rel = os.path.relpath(full, dump)
                target = os.readlink(full)
                if os.path.isabs(target):
                    # An absolute link points into another partition (/odm,
                    # /vendor_dlkm) or at a path that only exists on the device
                    # (/data, /mnt). Only the ones aimed at a file this list
                    # ships can be declared; the rest are created by the build
                    # (build/make/core/Makefile creates /vendor/odm and
                    # /vendor/lib/modules) or by init at runtime.
                    resolved = os.path.join(dump, target.lstrip('/'))
                    if not os.path.exists(resolved):
                        external.append((link_rel, target))
                        continue
                else:
                    resolved = os.path.normpath(os.path.join(dirpath, target))
                    if not os.path.exists(resolved):
                        dangling.append(link_rel)
                        continue
                symlinks.setdefault(os.path.relpath(resolved, dump), []).append(link_rel)
                # a symlinked directory should not be walked twice
                if os.path.isdir(full) and name in dirnames:
                    dirnames.remove(name)

    # ---- section 1: inherited (creek) entries that exist here -----------
    seen = set()
    inherited = []
    kept = dropped = 0
    if args.base:
        section = []
        for kind, payload in parse_pf(args.base):
            if kind == 'entry':
                line, dst = payload
                excluded_here = excluded(dst)
                if not excluded_here and dst not in seen and exists(dump, dst):
                    section.append(line)
                    seen.add(dst)
                    kept += 1
                else:
                    dropped += 1
            elif kind == 'comment' and is_scaffold(payload):
                continue
            else:
                section.append(payload)
        # drop repeated blanks and any blank left where scaffolding was cut
        inherited = []
        for item in section:
            if not item.strip() and inherited and not inherited[-1].strip():
                continue
            inherited.append(item)
        while inherited and not inherited[0].strip():
            inherited.pop(0)

    # ---- section 2: device-specific additions ---------------------------
    def unlisted(part, keep):
        out = []
        for rel, _ in walk_files(dump, part):
            if keep(rel) and rel not in seen:
                out.append(rel)
                seen.add(rel)
        return out

    odm_adds = unlisted('odm', lambda rel: rel != 'odm/etc/build.prop')
    vendor_adds = unlisted('vendor', lambda rel: not excluded(rel))

    # A base that came out of this generator already carries the additions
    # markers; keeping them where they are is what makes a regeneration
    # byte-identical when the firmware has nothing new in vendor/ or odm/.
    base_has_marker = bool(args.base) and any(
        kind == 'comment' and payload.startswith(ADDITIONS_MARKER)
        for kind, payload in parse_pf(args.base)
    )

    additions = []
    if odm_adds or vendor_adds:
        additions.append('')
        if base_has_marker:
            additions.append(f'# New in {args.firmware_label}')
            additions.append('')
            additions.extend(odm_adds)
            additions.extend(vendor_adds)
        else:
            additions.append(ADDITIONS_MARKER)
            additions.append('')
            additions.append('# ODM partition — device specific (props, panel, camera, thermal, SKU)')
            additions.extend(odm_adds)
            additions.append('')
            additions.append('# Vendor blobs not covered by the base list')
            additions.extend(vendor_adds)

    # ---- fold symlinks into their targets ------------------------------
    resolved_lines = []
    consumed = set()
    for line in inherited + additions:
        if line.startswith('#') or not line or line.endswith('/'):
            resolved_lines.append(line)
            continue
        dst = line[1:] if line.startswith('-') else line
        dst = dst.split(';')[0].split('|')[0]
        links = symlinks.get(dst)
        # A base list that already carries the symlink arg (regenerating from
        # an existing proprietary-files.txt rather than the creek seed) must
        # not get it appended twice.
        if links:
            consumed.add(dst)
        if links and ';SYMLINK=' not in line:
            values = []
            for link in sorted(set(links)):
                if os.path.dirname(link) == os.path.dirname(dst):
                    values.append(os.path.basename(link))
                else:
                    values.append(link)
            line += ';SYMLINK=' + ','.join(values)
        resolved_lines.append(line)

    # ---- write ---------------------------------------------------------
    header = [
        f'# Blobs extracted from zephyr {args.firmware_label} (Redmi Note 17 4G / p19a)',
        f'# Generated by tools/gen-proprietary-files.py — do not hand-edit; re-run it.',
        f'# Sections above "zephyr additions" are inherited from the creek list.',
        '',
    ]
    with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(header + resolved_lines).rstrip() + '\n')

    # ---- report --------------------------------------------------------
    total = sum(1 for l in resolved_lines if l and not l.startswith('#'))
    print(f'inherited entries kept : {kept}')
    print(f'inherited entries dropped (not in zephyr dump): {dropped}')
    print(f'total entries written  : {total}')
    print(f'symlinked entries      : {sum(1 for l in resolved_lines if ";SYMLINK=" in l)}')
    if dangling:
        print(f'warning: {len(dangling)} dangling symlinks skipped, e.g. {dangling[:3]}')
    print(f'links to another partition or a runtime path: {len(external)}')
    for link, target in external[:5]:
        print(f'  {link} -> {target}')
    unattached = sorted(set(symlinks) - consumed)
    print(f'links with no entry to attach to: {len(unattached)}')
    for target in unattached[:5]:
        print(f'  {target} (links: {", ".join(symlinks[target][:3])})')


if __name__ == '__main__':
    main()

#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

import re

from extract_utils.file import File
from extract_utils.fixups_blob import (
    BlobFixupCtx,
    blob_fixup,
    blob_fixups_user_type,
)

from extract_utils.main import (
    ExtractUtils,
    ExtractUtilsModule,
)


def explicit_root_user(
    ctx: BlobFixupCtx,
    file: File,
    file_path: str,
    *args,
    **kwargs,
):
    """Add `user root` to every service block that leaves the user out.

    Android 16's init refuses to parse a service with no user ("No user
    specified for service '...', so it would have been root"), and a service
    that never set one has always run as root, so this only writes the
    behaviour that already existed. The rc files below are stock blobs, so the
    edit has to happen at extraction time rather than in an edited copy.
    """
    with open(file_path) as f:
        lines = f.read().splitlines()

    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if not re.match(r'^\s*service\s', line):
            i += 1
            continue

        # The block runs to the next service/on/import keyword. Check the whole
        # block for an existing user, but put the new option right after the
        # command: the line may end in a backslash continuation, and comments
        # that introduce the next section sit between blocks.
        j = i + 1
        while j < len(lines) and not re.match(r'^\s*(service|on|import)\s', lines[j]):
            j += 1
        block = lines[i + 1:j]
        if any(re.match(r'^\s*user\s', b) for b in block):
            out.extend(block)
        else:
            k = i
            while lines[k].rstrip().endswith('\\'):
                k += 1
            out.extend(lines[i + 1:k + 1])
            out.append('    user root')
            out.extend(lines[k + 1:j])
        i = j

    if out != lines:
        with open(file_path, 'w') as f:
            f.write('\n'.join(out) + '\n')


def no_autostart(
    ctx: BlobFixupCtx,
    file: File,
    file_path: str,
    *args,
    **kwargs,
):
    """Add `disabled` to a stock service init would otherwise start at boot.

    qccsyshal@1.2-service is built against a protobuf the tree cannot supply:
    it imports the out-of-line protobuf 3.13 arena/string helpers
    (ArenaStringPtr::Set, Arena::AllocateAlignedWithHook,
    Arena::AllocateAlignedWithCleanup, VerifyUTF8, LogFatalSizeTooBig), which
    neither the platform's protobuf 4.25 nor the vendored 3.9.1 runtime exports.
    The linker rejects the executable, init restarts it every five seconds, and
    nothing in the tree declares or consumes the interface - so the stock
    `class hal` start only fills the crash buffer.
    """
    with open(file_path) as f:
        lines = f.read().splitlines()

    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.match(r'^\s*service\s', line):
            out.append(line)
            i += 1
            continue

        j = i + 1
        while j < len(lines) and not re.match(r'^\s*(service|on|import)\s', lines[j]):
            j += 1
        block = lines[i + 1:j]

        out.append(line)
        out.extend(block)
        if not any(re.match(r'^\s*disabled\s*$', b) for b in block):
            out.append('    disabled')
        i = j

    with open(file_path, 'w') as f:
        f.write('\n'.join(out) + '\n')


def _no_autostart() -> blob_fixup:
    return blob_fixup().call(no_autostart, need_tmp_dir=False)


def never_start(
    services: str,
    ctx: BlobFixupCtx,
    file: File,
    file_path: str,
    *args,
    **kwargs,
):
    """Mark stock services `disabled` and drop every action that starts them.

    These rc files come from MIUI and name SELinux domains the tree neither
    defines nor should define: mi_ric is Xiaomi's anti-tamper checker,
    batterysecret is PD charger authentication, and factory_services is a
    factory-test HAL. init cannot setexeccon() into a domain that does not
    exist, so each attempt dies with status 6 before exec'ing anything.

    The loop is what hurts: because these services register updatable
    components, init escalates through flags_health_check and restarts them
    every five seconds indefinitely - three services, each spawning a child
    plus a health-check exec per round. That fork/exec storm is the heat and
    the battery drain, not the daemons themselves.

    The seclabel is deliberately kept. Stripping it does not help: with no
    label init keeps its own context and the execve still fails, just with a
    different denial. Never starting the service is the only form that leaves
    init quiet.
    """
    names = set(services.split())
    with open(file_path) as f:
        lines = f.read().splitlines()

    out = []
    i = 0
    while i < len(lines):
        line = lines[i]

        action = re.match(r'^\s*(start|stop)\s+(\S+)\s*$', line)
        if action is not None:
            if action.group(2) not in names:
                out.append(line)
            i += 1
            continue

        if not re.match(r'^\s*service\s', line):
            out.append(line)
            i += 1
            continue

        j = i + 1
        while j < len(lines) and not re.match(r'^\s*(service|on|import)\s', lines[j]):
            j += 1
        block = lines[i + 1:j]

        out.append(line)
        out.extend(block)
        if (
            re.match(r'^\s*service\s+(\S+)', line).group(1) in names
            and not any(re.match(r'^\s*disabled\s*$', b) for b in block)
        ):
            out.append('    disabled')
        i = j

    if out != lines:
        with open(file_path, 'w') as f:
            f.write('\n'.join(out) + '\n')


def _never_start(*services: str) -> blob_fixup:
    return blob_fixup().call(never_start, ' '.join(services), need_tmp_dir=False)


def _root_user() -> blob_fixup:
    return blob_fixup().call(explicit_root_user, need_tmp_dir=False)


def unmapped_hidl_service(
    ctx: BlobFixupCtx,
    file: File,
    file_path: str,
    *args,
    **kwargs,
):
    """Drop the lazy-HAL mapping from a stock rc file.

    The interface these services advertise is only available as a blob;
    nothing in the tree builds a hidl_interface target for it, so init cannot
    resolve the `interface` line (host_init_verifier: "not in the known set of
    hidl_interfaces") and would refuse to start the service on demand. Removing
    it together with the `disabled` flag makes init start the service with its
    class at boot, which is what the stock build's lazy start achieved.
    """
    with open(file_path) as f:
        lines = f.read().splitlines()

    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.match(r'^\s*service\s', line):
            out.append(line)
            i += 1
            continue

        j = i + 1
        while j < len(lines) and not re.match(r'^\s*(service|on|import)\s', lines[j]):
            j += 1
        block = lines[i + 1:j]
        if not any(re.match(r'^\s*interface\s+\S+@\S+\s+\S+', b) for b in block):
            out.append(line)
            out.extend(block)
        else:
            out.append(line)
            out.extend(
                b for b in block
                if not re.match(r'^\s*interface\s+\S+@\S+\s+\S+', b)
                and not re.match(r'^\s*disabled\s*$', b)
            )
        i = j

    if out != lines:
        with open(file_path, 'w') as f:
            f.write('\n'.join(out) + '\n')


def _no_hidl_mapping() -> blob_fixup:
    return blob_fixup().call(unmapped_hidl_service, need_tmp_dir=False)


def mi_display_ueventd(
    ctx: BlobFixupCtx,
    file: File,
    file_path: str,
    *args,
    **kwargs,
):
    """Declare the mi_display subsystem so the FOD control node lands where the
    Goodix HAL looks for it.

    mi_disp registers its char device through a class devnode callback that
    returns "mi_display/disp_feature", so the kernel emits
    DEVNAME=mi_display/disp_feature. ueventd only honours that path when a
    subsystem block overrides the devname source to the sysfs devpath; without
    one it keeps the basename and creates /dev/disp_feature as 0600 root:root.
    libmifpext opens the hardcoded /dev/mi_display/disp_feature for FOD local
    HBM and for the display monitor thread that gates the FOD engine, so the
    open fails with ENOENT and enrollment waits out its 60 s timeout with the
    sensor never armed.

    Stock declares this block in system/etc/ueventd.rc, which the tree replaces
    with AOSP's copy, so it has to be re-added to the vendor rc that system's
    imports.
    """
    with open(file_path) as f:
        content = f.read()

    if 'subsystem mi_display' in content:
        return

    block = (
        '\n'
        'subsystem mi_display\n'
        '    devname uevent_devpath\n'
        '    dirname /dev/mi_display\n'
        '\n'
        '/dev/mi_display/*         0666   root       graphics\n'
    )

    anchor = ('subsystem mem_buf_vm\n'
              '    devname uevent_devpath\n'
              '    dirname /dev/mem_buf_vm\n')
    if anchor in content:
        content = content.replace(anchor, anchor + block, 1)
    else:
        content = content.rstrip('\n') + '\n' + block

    with open(file_path, 'w') as f:
        f.write(content)


def _mi_display_ueventd() -> blob_fixup:
    return blob_fixup().call(mi_display_ueventd, need_tmp_dir=False)


def drop_qti_video_decoders(
    ctx: BlobFixupCtx,
    file: File,
    file_path: str,
    *args,
    **kwargs,
):
    """Stop advertising the stock QTI video decoders.

    The stock Codec2 HAL (vendor.qti.media.c2@1.0-service) aborts inside
    C2BqBuffer while setting up the output surface. In a 23-minute capture of
    the YouTube app every fatal media failure was that one call:

        Codec2Client: setOutputSurface -- generation=... consumer usage=0x900
        ... 12 ms later ...
        tombstoned: crash request for pid <vendor qti media c2 service>
        Codec2Client: setOutputSurface -- transaction failed.
        CCodec: Codec2 component "c2.qti.vp9.decoder" died.
        MediaCodec: Codec reported err 0xffffffe0/DEAD_OBJECT

    7 of 7 failed transactions were c2.qti.vp9.decoder, and they start right
    after the first output buffer is imported ("Gralloc4: Adding additional
    valid usage bits"), i.e. in the buffer handoff, not in codec ranking: the
    same component also completes the very same call successfully between
    crashes. The service is HAL 1.0, so it has neither setOutputSurfaceWithSyncObj
    nor the deferred-deallocation workaround (b/322731059) that AOSP's client
    uses for Android 16 BLASTBufferQueue surfaces; the surface can be reused by
    the next component instance while the old one still owns buffers, and the
    vendor side has no way to signal that. Nothing in the framework can make
    that handoff safe, and the blob cannot be fixed.

    The same output path is the plausible source of the corrupt frames users
    see (green screen, flashing, video stuck on the thumbnail): the QTI target
    spec forces linear output ("platform_disable_ubwc": true,
    "dec_linear_color_format": 3, "vidc_disable_hdr": 3), so any mismatch in
    the buffer format the surface hands back produces exactly those artifacts.

    The same abort also hits the QTI AVC decoder. YouTube's own QoE log from
    the final build names it directly:

        reason.CODEC_INIT_REASON_SET_OUTPUT_SURFACE_FAILED,dec:c2.qti.avc.decoder
        error=...:e.j.CodecE;...;name.c2.qti.avc.decoder;sur.valid;esur.valid
        Codec2Client: createComponent(c2.qti.avc.decoder) -- transaction failed.

    so dropping VP9 alone did not fix playback: YouTube falls back to AVC for
    most streams and hits the same output-surface handoff. Drop the non-secure
    QTI AVC/HEVC/VP9 decoders and leave the .secure variants in place for DRM.
    AOSP's c2.android.avc / hevc / vp9 decoders (still in this list) take over.
    Decode then runs in the app process through the normal Codec2 client
    buffer queue and no graphic buffer crosses a HIDL boundary.
    """
    with open(file_path) as f:
        content = f.read()

    removed = 0
    replacement = (
        '\n        <!-- QTI AVC/HEVC/VP9 decoders are not advertised on this port: the\n'
        '             stock Codec2 HAL aborts while setting up the output surface.\n'
        '             See extract-files.py, drop_qti_video_decoders(). -->'
    )

    pattern = re.compile(
        r'\n[ \t]*<MediaCodec name="c2\.qti\.(?:avc|hevc|vp9)\.decoder(?:\.low_latency)?"[^>]*>'
        r'.*?</MediaCodec>',
        re.DOTALL,
    )

    def repl(match):
        nonlocal removed
        removed += 1
        return replacement if removed == 1 else ''

    patched = pattern.sub(repl, content)
    if removed == 0 or patched == content:
        return

    with open(file_path, 'w') as f:
        f.write(patched)


def _drop_qti_video_decoders() -> blob_fixup:
    return blob_fixup().call(drop_qti_video_decoders, need_tmp_dir=False)

# Fixups carried over from the creek tree: the same mivendor_sm6225 blobs need
# the same uprev shims on Android 16. Binary patches that creek applied to its
# own Codec2/QCRIL blobs are deliberately NOT copied here — those depend on the
# exact binary in the dump and must be re-derived (and re-verified) for zephyr.
blob_fixups: blob_fixups_user_type = {
    ('vendor/lib64/hw/com.qti.chi.override.so',
     'vendor/lib64/libmialgoengine.so',
     'vendor/lib64/hw/camera.qcom.so'): blob_fixup()
        .add_needed('libprocessgroup_shim.so'),

    # libqcodec2_core.so imports the one-argument
    # _C2FenceFactory::CreateSyncFence(int). The stock libcodec2_vndk.so in the
    # dump already defines that symbol (a 4-byte thunk into its own two-argument
    # implementation), so the blob resolves it on its own. Do NOT reintroduce a
    # DT_NEEDED shim here: it can only forward to CreateSyncFence(int, bool),
    # which the stock vendor libcodec2_vndk does not export, so the shim fails
    # to dlopen and takes the whole QTI Codec2 store down with it.

    # Stock libcodec2_vndk still imports the pre-Android-14
    # GraphicBufferMapper::lock/unlock ABI; libui_shim (vendor copy) supplies it.

    ('vendor/lib/libcodec2_vndk.so',
     'vendor/lib64/libcodec2_vndk.so'): blob_fixup()
        .add_needed('libui_shim.so'),

    # The firmware's libgui_vendor.so still imports ui::StaticDisplayInfo's
    # Flattenable API, which libui dropped when the struct became an AIDL
    # parcelable. Nothing that loads it can link until the symbol resolves,
    # and the only consumers are the display feature HAL and daemon that drive
    # FOD high-brightness mode; see libui/StaticDisplayInfo.cpp.
    'vendor/lib64/libgui_vendor.so': blob_fixup()
        .add_needed('libui_shim.so'),

    # Built against protobuf 3.9; see libprotobuf/CopyWithSourceCheck.cpp.
    'system_ext/lib64/vendor.qti.hardware.qccsyshal@1.2-halimpl.so': blob_fixup()
        .add_needed('libprotobuf-qccshim.so'),

    # Its remaining protobuf imports are 3.13-only and nothing consumes it;
    # see no_autostart().
    'system_ext/etc/init/vendor.qti.hardware.qccsyshal@1.2-service.rc': _no_autostart(),

    ('vendor/bin/hw/android.hardware.security.keymint-service-qti',
     'vendor/lib64/libqtikeymint.so'): blob_fixup()
        .add_needed('android.hardware.security.rkp-V3-ndk.so'),

    'vendor/lib64/vendor.libdpmframework.so': blob_fixup()
        .add_needed('libhidlbase_shim.so'),

    # Stock's system/etc/ueventd.rc declares the mi_display subsystem and the
    # tree ships AOSP's copy instead; see mi_display_ueventd() above.
    'vendor/etc/ueventd.rc': _mi_display_ueventd(),

    # The stock QTI video decoders crash the Codec2 HAL in the output-surface
    # buffer handoff; see drop_qti_video_decoders() above. Both variants are
    # patched so a target_variant change cannot bring the crash back.
    ('vendor/etc/media_codecs_bengal_v1.xml',
     'vendor/etc/media_codecs_khaje_v0.xml'): _drop_qti_video_decoders(),

    # Stock init scripts whose services do not declare a user; see
    # explicit_root_user() above.
    'vendor/etc/init/android.hardware.wifi.supplicant-service.rc': _root_user(),
    'vendor/etc/init/boringssl_self_test.rc': _root_user(),
    'vendor/etc/init/init.boot_mode.rc': _root_user(),
    'vendor/etc/init/minidump.rc': _root_user(),
    'vendor/etc/init/netmgrd.rc': _root_user(),
    'vendor/etc/init/vendor.dpmd.rc': _root_user(),
    'odm/etc/init/vendor.xiaomi.hardware.aidl.mtdservice-service.rc': _root_user(),

    # MIUI services whose seclabel domain the tree does not define; see
    # never_start() above.
    'vendor/etc/init/mi_ric.rc': _never_start(
        'mi_ric_init', 'mi_ric_run', 'mi_ric_file', 'mi_ric_snapshot',
    ),
    'vendor/etc/init/init.batterysecret.rc': _never_start('batterysecret'),
    'vendor/etc/init/factorybsp_service_qcom.rc': _never_start(
        'interfaces.factoryInterface-V1-service',
    ),

    # Stock rc files whose HIDL interface exists only as a blob; see
    # unmapped_hidl_service() above. The camera postproc interface is not here:
    # vendor/qcom/opensource/interfaces builds it.
    'vendor/etc/init/dpmQmiMgr.rc': _no_hidl_mapping(),
    'vendor/etc/init/init.embmssl_server.rc': _no_hidl_mapping(),
    'vendor/etc/init/vendor.qti.hardware.alarm@1.0-service.rc': _no_hidl_mapping(),
    'vendor/etc/init/vendor.qti.hardware.dsp@1.0-service.rc': _no_hidl_mapping(),
    'vendor/etc/init/vendor.qti.hardware.factory@1.0-service.rc': _no_hidl_mapping(),
    'vendor/etc/init/vendor.qti.hardware.limits-service.rc': _no_hidl_mapping(),
    'vendor/etc/init/vendor.qti.hardware.wifi.wifilearner@1.0-service.rc': _no_hidl_mapping(),
}

module = ExtractUtilsModule(
    'zephyr',
    'xiaomi',
    blob_fixups=blob_fixups,
    check_elf=False,
)

if __name__ == '__main__':
    utils = ExtractUtils.device(module)
    utils.run()

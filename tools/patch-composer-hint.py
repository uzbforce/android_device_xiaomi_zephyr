#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Neutralise sdm::HWCDisplayBuiltIn::HandleLargeCompositionHint(bool) in the
# prebuilt Qualcomm composer.
#
# CPUHint::Init() fails on zephyr, so cpu_hint_ stays null. The caller does
#
#     hwc_display->HandleLargeCompositionHint(!hwc_display->NeedsLargeCompPerfHint());
#
# and NeedsLargeCompPerfHint() starts with `if (!cpu_hint_) return false;`. The
# inverted result is therefore `true`, and the hint path then dereferences the
# null cpu_hint_ without a guard:
#
#     Fatal signal 11 (SIGSEGV), fault addr 0x0000000000000058
#     #00 pc ... vendor.qti.hardware.display.composer-service
#         (sdm::HWCDisplayBuiltIn::HandleLargeCompositionHint(bool)+68)
#     #01 pc ... (sdm::HWCSession::ValidateDisplayInternal(unsigned long, ...)+632)
#
# That kills SurfaceFlinger and refork system_server, so the device loops on
# the boot animation. vendor.display.enable_perf_hint_large_comp_cycle does not
# help: NeedsLargeCompPerfHint() bails on the null cpu_hint_ before it ever
# looks at the property, which is why both 0 and 1 crash identically.
#
# The function only sends CPU perf hints and has no other side effects, so
# replacing its first instruction (`sub sp, sp, #0x40`) with `ret` is safe.
# Re-run this after regenerating vendor/xiaomi/zephyr from the stock dump.
#
# Usage: patch-composer-hint.py [path-to-composer-service]

import os
import struct
import sys

DEFAULT = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../../vendor/xiaomi/zephyr/proprietary/vendor/bin/hw/"
        "vendor.qti.hardware.display.composer-service")

ENTRY = 0x6AE8C          # HWCDisplayBuiltIn::HandleLargeCompositionHint(bool)
PROLOGUE = 0xD10103FF    # sub sp, sp, #0x40
RET = 0xD65F03C0         # ret


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    path = os.path.realpath(path)
    data = bytearray(open(path, "rb").read())

    word = struct.unpack_from("<I", data, ENTRY)[0]
    if word == RET:
        print("%s: already patched" % path)
        return 0
    if word != PROLOGUE:
        print("%s: unexpected instruction %#x at %#x - blob changed, "
              "re-check the function offset" % (path, word, ENTRY))
        return 1

    struct.pack_into("<I", data, ENTRY, RET)
    open(path, "wb").write(data)
    print("%s: patched HandleLargeCompositionHint at %#x" % (path, ENTRY))
    return 0


if __name__ == "__main__":
    sys.exit(main())

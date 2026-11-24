# android_device_xiaomi_zephyr

Device tree for the **Redmi Note 17 4G** — codename `zephyr`, Xiaomi project `p19a`,
SM6225-AF (Snapdragon 6s 4G Gen 2, `bengal`). Target: **LineageOS 23.2** (Android 16).

Built from the stock firmware `zephyr_global_images_OS3.0.311.0.WBUMIXM_16.0`
(HyperOS 3.0.311.0.WBUMIXM, Android 16 / SDK 36, kernel 5.15.194-android13-8).
The blob list was first derived from 3.0.310.0 and checked against this one: the
inventory is unchanged, 84 blobs differ in content, and the vendor repo carries
the 3.0.311.0 versions.

A verified hardware inventory — panel, touch, cameras, fingerprint, NFC, audio,
charging, sensors, partitions — is in [docs/HARDWARE.md](docs/HARDWARE.md).
Everything there was read out of the firmware, not from spec sheets.

## Status

The tree builds end to end: `mka bacon` produced
`lineage-23.2-********-UNOFFICIAL-zephyr.zip` plus boot, init_boot,
vendor_boot, dtbo, vbmeta and the super images. What is left is on-device
bring-up, not the build — see *Known gaps*. Every ROM-side fix the build needed
is a patch in
[lineage_patches_zephyr](https://github.com/uzbforce/lineage_patches_zephyr).

| Piece | State |
|---|---|
| `proprietary-files.txt` | generated, 3631 entries, all verified present in the dump; the vendor repo builds through `extract_utils` and installs without a duplicate destination |
| Partition/super geometry | measured from stock `super.img` |
| fstab, rootdir init scripts | taken from the stock vendor partition |
| Device props | FOD geometry, Wi-Fi chip, density and the graphics driver (`ro.hardware.egl`, `ro.hardware.vulkan`, `ro.opengles.version`) taken from stock props, plus the USB composition the stock `vendor/build.prop` carried |
| VINTF | device manifest reproduced from the stock vendor manifest (53 HALs / 68 instances); platform matrix comes from `qcom-caf/common`, and `configs/vintf/framework_compatibility_matrix.xml` declares the Xiaomi/QTI HALs the AOSP matrices do not know |
| Kernel | the stock prebuilt tree is the default and verified against the firmware; the source route is parked - Xiaomi's OSS drop has no `techpack/`, so a source-built kernel would have no display, GPU, video or audio modules |
| SEPolicy | skeleton, plus the file-contexts rule for the QTI power HAL |
| Platform HAL tree (`sm6225` caf) | not shipped by LineageOS 23.2; pinned manifest in `local_manifests/zephyr.xml`, without the display tree (see *Platform repos*) |
| Overlays (Xiaomi RROs) | ported: 11 source RROs in `overlay/`, regenerated from the stock APKs and diffed against them |

Bring-up so far: the first boot stopped at the OEM logo because the generated
`vendor/build.prop` carried no graphics driver selection, and `libEGL` aborts in
`Loader::open()` when neither `persist.graphics.egl`, `ro.hardware.egl` nor
`ro.board.platform` names an implementation — which took SurfaceFlinger and
zygote with it. The three properties stock sets now come from
`configs/properties/vendor.prop`. The boot after that reached zygote but had no
binder context manager on `/dev/vndbinder`: the stock `vndservicemanager`
prebuilt aborted in `ServiceManager::listServices`, so every vendor HAL failed
to register and SurfaceFlinger fell back to a HIDL composer this vendor does not
ship. The daemon is now the one `frameworks/native` builds (see *Blob list
notes*).

The next stopper was the power HAL. system_server blocked in
`PowerManagerService.nativeInit` on `android.hardware.power.IPower/default` and
the watchdog killed it after 66 s: the QTI power rc declared no `interface
aidl` line, so init answered `ctl.interface_start` with
`PROP_ERROR_HANDLE_CONTROL_MESSAGE`, and the stock prebuilt that might have
served it was a second `vendor.power` service. The rc declares the interface
now (a patch in the patches repo) and the stock duplicate is out of the blob
list. adb had been missing for a different reason: no composition was chosen
before system_server, so the gadget was never bound and adbd never started;
`configs/properties/vendor.prop` now sets `mass_storage,adb` on init's
configfs path. The vendor image built before those two blob edits also had to
be repacked by hand, because the incremental build reused a
`vendor_intermediates/file_list.txt` from before them and left 28 staged files
out of the image.

The power service still could not be exec'd after that: the platform labels
`android.hardware.power-service` and the AOSP example, not the `-qti` name, so
the QTI binary fell back to `vendor_file` and init found no domain transition
for it (`Could not ctl.interface_start ... incorrect label or no domain
transition`). `sepolicy/vendor/file_contexts` now labels it
`hal_power_default_exec`.

The FOD path was missing three separate things at once. `mi_disp` registers its
character device through a class `devnode` callback that returns
`mi_display/disp_feature`, so the kernel emits `DEVNAME=mi_display/disp_feature`
— but ueventd only keeps a path of that shape when a `subsystem` block switches
`devname` to `uevent_devpath`, and stock declares that block in
`/system/etc/ueventd.rc`, which the tree replaces with AOSP's copy. Without it
ueventd kept the basename and created `/dev/disp_feature` as `0600 root:root`, so
every `open("/dev/mi_display/disp_feature")` in the Goodix `libmifpext` failed
with `ENOENT`; `extract-files.py` now re-adds the block to
`vendor/etc/ueventd.rc`. The Xiaomi display-feature daemon
(`/vendor/bin/displayfeature`, root, `late_start`, started from the
`surfaceflinger=running` property) and its HIDL HAL had no `file_contexts` label
at all, so init never transitioned into a domain and the native
`DisplayFeatureControl` service — the one `libmifpext` resolves for FOD
local-HBM — was never registered with `vndservicemanager`. Both now have domains
(permissive while their undocumented access sets are unknown), a
`vndservice_contexts` entry and a VINTF fragment. Finally `libmifpext` resolves
`vendor.xiaomi.hardware.touchfeature::ITouchFeature` to arm the touch
controller's FOD mode and had no permission for it, so registration exited with
`GF_ERROR_GENERIC, errno=1012` and init logged
`Service 'vendor.fps_hal' exited with status 1`;
`sepolicy/vendor/hal_fingerprint_default.te` grants it now.

## Layout

```
BoardConfig.mk          # geometry, kernel wiring, AVB, filesystems
device.mk               # packages, configs, props
lineage_zephyr.mk       # product definition (Lineage 23.2)
AndroidProducts.mk      # lunch targets
power/                  # power HAL extension: double-tap-to-wake
audio/                  # audio policy: the BT A2DP ports moved out of primary
bluetooth-audio/        # BT audio provider factory, registered by its own service
configs/idc/            # UDFPS input device configuration
configs/properties/     # per-partition props
configs/vintf/          # device manifest (DEVICE_MANIFEST_FILE) and the device
                        # framework matrix for the Xiaomi/QTI HALs
rootdir/                # fstab.qcom + stock init.qcom*.rc + Android.mk
sepolicy/               # skeleton (vendor + private)
overlay/                # source RROs (regenerated by tools/port-overlays.py)
proprietary-files.txt   # blob list, generated
extract-files.py        # extract_utils entry point (blob fixups)
setup-makefiles.py      # regenerate vendor makefiles only
lineage.dependencies    # points breakfast at the vendor repo
local_manifests/        # sm6225 platform repos, pinned (copy into .repo/local_manifests)
tools/                  # extraction, blob-list, drift-check and overlay tools
docs/HARDWARE.md        # verified hardware inventory
```

## Regenerating the vendor repo

The vendor repo (`vendor/xiaomi/zephyr`) is generated, not committed here.

1. Unpack the stock package:

   ```bash
   ./tools/extract-firmware.sh /path/to/zephyr_global_images_OS3.0.311.0.WBUMIXM_16.0 work
   ```

   This needs `simg2img`, `lpunpack`, `fsck.erofs` and `dtc`. The script header
   documents how to build the last two without root. It reuses `work/super.raw.img`
   and `work/parts/` when they are already there — only the partitions are
   re-extracted, which is the part that is cheap to redo. The stock `system.img`
   is built system-as-root (its `/init`, `/etc` and `/bin` are symlinks into an
   inner `/system`), so the inner directory is promoted to `work/root/system`
   and the image root is kept as `work/root/system_root`, the same layout
   `extract_utils` produces.
2. Check the blob list against a new dump before regenerating:

   ```bash
   ./tools/check-blob-drift.py --dump work/root \
       --vendor ../android_vendor_xiaomi_zephyr
   ```

   It reports blobs the dump no longer has, dump files the list does not cover,
   and — comparing against the vendor repo, which holds the previous firmware's
   blobs — which listed blobs changed content. That is how the 3.0.310.0 →
   3.0.311.0 delta was measured: 0 dropped, 0 added, 84 changed.

3. (Optional) regenerate `proprietary-files.txt` from the dump:

   ```bash
   ./tools/gen-proprietary-files.py --dump work/root \
       --base proprietary-files.txt \
       --firmware-label OS3.0.311.0.WBUMIXM \
       --out proprietary-files.txt
   ```

   Regenerating from the current list is byte-identical when the firmware adds
   nothing new in `vendor/` or `odm/`; new blobs land in a `# New in <firmware>`
   block. To rebuild the list from scratch instead, the seed is
   `Saslowki/android_device_xiaomi_creek@sixteen-axion`.
   Creek is the right seed: 82 % of its blob paths exist verbatim in zephyr's
   firmware, versus 73 % for sapphire, because both phones share the
   `mivendor_sm6225_global` vendor image.

4. Run extraction from an AOSP/Lineage checkout where this tree lives at
   `device/xiaomi/zephyr` (the generated repo is published at
   [uzbforce/android_vendor_xiaomi_zephyr](https://github.com/uzbforce/android_vendor_xiaomi_zephyr),
   so in practice you only need this when the firmware changes):

   ```bash
   cd device/xiaomi/zephyr
   export PATH=$PWD/../../../out/host/linux-x86/bin:$PATH   # lpunpack/lpdump
   ./extract-files.py --keep-dump /path/to/work/root   # writes vendor/xiaomi/zephyr
   git -C ../../../vendor/xiaomi/zephyr checkout -- README.md   # see below
   ./setup-makefiles.py                                # makefiles only
   ```

   `extract_utils` wipes everything in the vendor repo except dot-entries before
   copying, which is what prunes blobs a firmware dropped — but it takes the
   repo's hand-written `README.md` with it, so restore that one file
   afterwards.

## Kernel

Xiaomi published both halves for this device:

- kernel: `MiCode/Xiaomi_Kernel_OpenSource`, branch **`zephyr-w-oss`**
  (defconfigs `vendor/zephyr_GKI.config` and `vendor/zephyr_consolidate.config`)
- devicetree: `MiCode/kernel_devicetree`, branch **`zephyr-w-oss`**

Clone the kernel to `kernel/xiaomi/zephyr` and merge the devicetree repo into
`arch/arm64/boot/dts/vendor`. `BoardConfig.mk` expects exactly those paths, and
the same tree ships the module lists the build needs — nothing about the module
split is guessed any more: `modules.list.msm.zephyr` (first-stage load order),
`modules.vendor_blocklist.msm.zephyr`, `modules.systemdlkm_blocklist.msm.zephyr`.
That first-stage list has 102 entries and differs from the stock ramdisk's
`modules.load` in ten names (Xiaomi adds `perf_helper.ko`, `binder_prio.ko`,
`bootinfo.ko`, …), which is the expected delta between the two builds of the
same kernel.

### The prebuilt route (recommended for a first boot)

The firmware already contains everything a bootable pair needs, so the kernel can
stay out of the build completely:

```bash
./tools/gen-prebuilt-kernel.py --dump work/root \
    --firmware /path/to/zephyr_global_images_OS3.0.311.0.WBUMIXM_16.0 \
    --out ../zephyr-kernel
```

It assembles `device/xiaomi/zephyr-kernel` (or wherever `--out` points) from the
stock images, verifying as it goes that the Image is an arm64 Linux, that every
DTBO entry fits, that every module is an ELF and that every blocklist line is a
well-formed `blocklist <name>` record:

| Path | Contents |
|---|---|
| `kernel` | stock `Image`, 5.15.194-android13-8 |
| `dtbs/dtbo.img` | stock DTBO, 70 entries |
| `dtbs/dtb/` | 27 base DTBs from `vendor_boot.img` |
| `vendor_dlkm/` | 268 modules + `modules.load` (268 entries, de-duplicated) + `modules.blocklist` |
| `system_dlkm/` | `zram.ko`, `zsmalloc.ko` + `modules.load` |
| `vendor_ramdisk/` | 295 modules + `modules.load` (102) + `modules.load.recovery` (296) + `modules.blocklist` |

Then set `ZEPHYR_USE_PREBUILT_KERNEL := true` (and `ZEPHYR_PREBUILT_KERNEL_PATH`
if the tree is not at `device/xiaomi/zephyr-kernel`); both are `?=` defaults, so
they can also be passed to `m`. The tree has to stay inside the source tree —
`BOARD_PREBUILT_DTBOIMAGE` is read through a blueprint glob, and soong panics
with an unrelated-looking stack trace on a path outside it, so `BoardConfig.mk`
rejects an absolute path up front. `BoardConfig.mk` feeds the modules and the load
lists into the usual `BOARD_*_KERNEL_MODULES(_LOAD)` variables, which is what
puts `lib/modules` and `modules.load` on vendor_dlkm, system_dlkm and the vendor
ramdisk — the same partitions, the same lists and the same binaries as the
stock image, so the vendor blobs stay ABI-compatible with the kernel by
construction. If the flag is set and the tree is missing, the build stops with a
message instead of silently building a ramdisk without modules.

The kernel image itself is installed as `$(TARGET_PREBUILT_KERNEL):kernel`, a
copy file: the boot image and the vintf kernel check both read the kernel from
`$(PRODUCT_OUT)/kernel`, and the copy rule `kernel.mk` defines for that path is
keyed on an `INSTALLED_KERNEL_TARGET` that is still empty while `kernel.mk` is
parsed, so on this tree it never materialises — without the copy file the build
dies on `'out/target/product/zephyr/kernel' ... missing and no known rule to
make it`.

The kernel's uapi headers are the one part of the kernel that still comes from
somewhere else: the display HALs include `<linux/msm_ion.h>` and
`<linux/dma-buf.h>`, which no userspace package ships, and they get them through
`TARGET_BOARD_KERNEL_HEADERS`, which `BoardConfig.mk` points at
`zephyr-kernel/kernel-headers`. The directory name has to end in `kernel-headers`
(`build/make/core/config.mk` enforces it) and the directory holds the uapi set of
the same 5.15 zephyr kernel, produced once from the source:

```bash
device/xiaomi/zephyr/tools/gen-kernel-headers.sh
```

`tools/gen-kernel-headers.sh` runs `headers_install` into a scratch `out-hdr`,
and then does the step a hand-rolled copy misses: it sanitizes `asm/signal.h`
and `asm-generic/signal.h` with `bionic/libc/kernel/tools/clean_header.py`, the
same thing `vendor/lineage/tools/clean_headers.sh` does for an inline build.
The exported `asm-generic/signal.h` otherwise defines `struct sigaction`, and
because `TARGET_BOARD_KERNEL_HEADERS` is added as an `-isystem` to every module
that includes a libc header, the first kernel header to be reached wins and the
build dies with `redefinition of 'sigaction'` — which is exactly what happened
to `libqcompostprocbundle` before the script existed.

That is the only reason the source clone appears on this route; with it in place
`kernel.mk` would build the kernel itself, so the branch also sets
`TARGET_FORCE_PREBUILT_KERNEL := true`.

### Reading a boot that fails

The stock DT spends the whole 2 MB `ramoops_region` on `pmsg-size`, so the kernel
console and the panic dump have no pstore zone: a boot that dies leaves
`/sys/fs/pstore` empty in recovery whether it panicked or hung, and there is
nothing to read. `PSTORE_RAM` and `PSTORE_CONSOLE` are both in the stock Image
(`ramoops_probe`, `ramoops_init_prz` and `pstore_console_write` are in its
kallsyms), the node simply never asks for those zones:

```bash
./tools/patch-ramoops-dt.py device/xiaomi/zephyr-kernel
m vendorbootimage
```

It rewrites every DTB that carries the node to `record-size = 0x40000`,
`console-size = 0x80000` and `pmsg-size = 0x80000` — 2 MB in total, unchanged —
and keeps the stock blobs in `dtbs/.dtb-stock/`. `vendor_boot.img` then carries a
`console-ramoops-0` ring that survives a reset and records the kernel log,
init's `LOG()` lines included, so `cat /sys/fs/pstore/console-ramoops-0` in
recovery shows what the failing boot was doing. On Windows `cmd` quote nothing:
it passes single quotes through to adb, and mksh then looks for one command
named `ls -l /sys/fs/pstore`, so write `adb shell ls -l /sys/fs/pstore` and dump
the log with `adb exec-out cat /sys/fs/pstore/console-ramoops-0 > ramoops.txt`.
Re-run it after
`tools/gen-prebuilt-kernel.py`, which copies the DTBs out of the firmware
verbatim.

### The source route

Leave `ZEPHYR_USE_PREBUILT_KERNEL` false and the kernel is built from
`kernel/xiaomi/zephyr` with the lists above — but that route cannot produce a
usable kernel for this device, which is why `BoardConfig.mk` defaults to the
prebuilt tree. `zephyr-w-oss` has no `techpack/` tree: 71434 files and not one
of them is `techpack/display`, `techpack/audio` or `techpack/video`. The stock
`vendor_dlkm` carries what those trees build — `msm_drm.ko`, `msm_kgsl.ko`,
`msm_video.ko`, `q6_dlkm.ko`, `audio_pkt_dlkm.ko`, `lpassaudiocc-sm6115.ko`, …
(268 modules) — so a kernel from the OSS tree has no display, GPU, video or
audio, and the HALs that include the techpack uapi headers (`libqcompostprocbundle`
wants `<sound/audio_effects.h>`, the sm6225 SDE code wants
`<display/drm/sde_drm.h>`) cannot be compiled either. Both are taken from the
vendor repo's blobs instead.

The remaining differences the source route would show — the system_dlkm/
vendor_dlkm split (the OSS lists send everything to vendor_dlkm, the stock keeps
`zram.ko`/`zsmalloc.ko` on system_dlkm) — are only observable once there is a
techpack to build with.

One file in that tree needs a local edit, on both routes, before its headers are
exported: `include/uapi/linux/sched/types.h` defines `struct sched_param`, and
bionic defines the same struct in `<sched.h>`. Anything that ends up with both
— a QTI module that includes `<pthread.h>` and reaches a kernel uapi header,
such as `libipanat` through `<linux/msm_ipa.h>` — fails to compile with
`redefinition of 'sched_param'`. Putting the definition inside
`#ifdef __KERNEL__` leaves the kernel compile untouched and drops it from the
headers `make headers_install` writes out (`scripts/unifdef` runs with
`-U__KERNEL__`), which is exactly what
`bionic/libc/kernel/uapi/linux/sched/types.h` ships:

```bash
cd kernel/xiaomi/zephyr
python3 - <<'EOF'
p = 'include/uapi/linux/sched/types.h'
s = open(p).read()
old = "struct sched_param {\n\tint sched_priority;\n};\n"
assert old in s, 'already patched?'
open(p, 'w').write(s.replace(old, '#ifdef __KERNEL__\n' + old + '#endif\n'))
EOF
```

The guard has to be in place before `kernel-headers/` is produced from the same
tree (the snippet in the prebuilt section above); a directory copied earlier
still carries the unguarded struct and has to be rebuilt or edited by hand.

### What the build has to produce

Same shape as the stock firmware, measured from it:

| Image | Size | Notes |
|---|---|---|
| `boot.img` | 100663296 | Image only, header v4, no ramdisk |
| `vendor_boot.img` | 100663296 | vendor ramdisk: first-stage fstab, module lists, bootconfig |
| `init_boot.img` | 8388608 | the GKI ramdisk |
| `dtbo.img` | 25165824 | 70 entries |

Two of those are wired explicitly because the first draft of `BoardConfig.mk`
missed them: `BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE` (without it the build never
creates a vendor ramdisk, so first-stage mount has no fstab and no module lists)
and the copy of the fstab into `/first_stage_ramdisk/fstab.qcom` in `device.mk`.
First-stage mount runs before `/vendor` is mounted and `ro.hardware` is `qcom`
(`BOARD_BOOTCONFIG`), so `fstab.qcom` is the name init looks for; the `dtbs`
stay out of the boot images, the bootloader reads the DTBO from its own
partition.

## Building

### From a fresh checkout

These are the exact inputs the working build used. The three repos are cloned
into the tree; the stock firmware and a one-time kernel source clone provide
the prebuilt kernel and its uapi headers.

```bash
repo init -u https://github.com/LineageOS/android.git -b lineage-23.2
git clone -b lineage-23.2 https://github.com/uzbforce/android_device_xiaomi_zephyr device/xiaomi/zephyr
cp device/xiaomi/zephyr/local_manifests/zephyr.xml .repo/local_manifests/
repo sync -c -j8 --force-sync
git clone -b lineage-23.2 https://github.com/uzbforce/android_vendor_xiaomi_zephyr vendor/xiaomi/zephyr
git clone -b lineage-23.2 https://github.com/uzbforce/xiaomi_zephyr_cusrom_patches xiaomi_zephyr_cusrom_patches
git clone -b zephyr-w-oss https://github.com/MiCode/Xiaomi_Kernel_OpenSource kernel/xiaomi/zephyr
./xiaomi_zephyr_cusrom_patches/apply.sh .
```

The local manifest pins the sm6225 platform projects and the MindTheGapps tree
(`vendor/gapps`) that `lineage_zephyr.mk` inherits; without it product config
stops on the missing GApps makefile. The kernel source clone is not built: it
is what `tools/gen-kernel-headers.sh` exports the uapi headers from.

Generate the prebuilt kernel tree from the same stock package, export the
headers, and apply the ramoops patch the running build uses:

```bash
device/xiaomi/zephyr/tools/extract-firmware.sh /path/to/zephyr_global_images_OS3.0.311.0.WBUMIXM_16.0 work
device/xiaomi/zephyr/tools/gen-prebuilt-kernel.py --dump work/root --firmware /path/to/zephyr_global_images_OS3.0.311.0.WBUMIXM_16.0 --out device/xiaomi/zephyr-kernel
device/xiaomi/zephyr/tools/gen-kernel-headers.sh
device/xiaomi/zephyr/tools/patch-ramoops-dt.py device/xiaomi/zephyr-kernel
```

Then build:

```bash
source build/envsetup.sh
lunch lineage_zephyr-bp4a-user
mka bacon
```

The working image is a `user` build. For a `userdebug` image with ADB and the
removable system tools in recovery, use
`lunch lineage_zephyr-bp4a-userdebug` instead.

### Before the first sync

1. Both repos are on `lineage-23.2`; the branches were renamed from `main` and
   `lineage.dependencies` pins the vendor repo to the new name. A checkout that
   still has `main` in `.repo/manifests` will not resolve them, so re-run
   `repo init -b lineage-23.2` (or init fresh) after the rename.
2. `cp device/xiaomi/zephyr/local_manifests/zephyr.xml .repo/local_manifests/`
   **before** `repo sync` (clone the device tree first, as in *From a fresh
   checkout*) — see *Platform repos* for why. Without it the build
   configures but the sm6225 HALs are missing; `vendorsetup.sh` patches the
   stock qcom-caf tree instead, and `BoardConfig.mk` falls back to the legacy-UM
   policy with a warning.
3. The only other input is a one-time kernel source clone under
   `kernel/xiaomi/zephyr`, used to export the uapi headers the prebuilt route
   needs; the kernel image itself is not built from it. The tooling deps
   (`dtc`, `simg2img`, `lpunpack`, `fsck.erofs`, `aapt2`) are only needed when
   regenerating the vendor repo or the overlays.

The device and vendor repos this tree needs live on the `lineage-23.2` branch;
the ROM-side patches are the third (see *From a fresh checkout* above):

```bash
git clone -b lineage-23.2 https://github.com/uzbforce/android_device_xiaomi_zephyr \
    device/xiaomi/zephyr
```

The vendor repo is published too, so `breakfast zephyr` can fetch it via
`lineage.dependencies` (which pins the same branch). If it does not resolve,
pin it manually:

```xml
<!-- .repo/local_manifests/vendor.xml (keep it separate from zephyr.xml,
     which carries the platform projects) -->
<project name="uzbforce/android_vendor_xiaomi_zephyr"
         path="vendor/xiaomi/zephyr"
         remote="github"
         revision="lineage-23.2" />
```

```bash
source build/envsetup.sh
breakfast zephyr          # or: lunch lineage_zephyr-bp4a-userdebug
mka bacon
```

Use `breakfast zephyr`. Android 16's `lunch` wants
`<product>-<release>-<variant>`, and `lineage_zephyr-userdebug` alone is
rejected with *"Valid combos must be of the form
<product>-<release>-<variant>"*; `breakfast` reads the release (`bp4a`) out of
`vendor/lineage/vars/aosp_target_release` and builds the full combo for you.

`vendorsetup.sh` decides the platform setup before the build starts. If
`hardware/qcom-caf/common` is the forked tree (from `local_manifests/zephyr.xml`,
see *Platform repos*) it reports that and does nothing; on a stock checkout it
patches the three files so `bengal` counts as a 5.15 platform under
`TARGET_BOARD_SUFFIX := _515`, `QCOM_HARDWARE_VARIANT` becomes `sm6225`, and
sepolicy picks up the sm6225 directory. Both paths were tested against the real
LineageOS 23.2 `BoardConfigQcom.mk`, `qcom_defs.mk` and
`os_pickup_sepolicy_vndr.mk`, and running it twice is a no-op.

### Recovery

Recovery here is Lineage/AOSP recovery, not TWRP. Touch is brought up from the
stock `vendor_dlkm` modules by second-stage recovery init; volume/power remain
available as fallback. The panel is a `focaltech,ft3683g` SPI node, whose driver
is `ft3683g_spi`; `focaltech_fts` is the I2C driver for the other panel variant
(`focaltech,fts_ts`) and cannot load on the stock kernel (`qts_client_register`
is not exported).

`ft3683g_spi` must not be added to `modules.load.recovery`: in the first stage
it probes before its dependencies are loaded and panics the kernel, so the OEM
logo goes black and the bootloader loops back into recovery with the BCB still
set; only a full stock flash clears it. `modules.load.recovery` therefore stays
the stock 296-entry list. Recovery does not mount the `vendor_dlkm` partition,
so the three modules are staged at `recovery/root/vendor_dlkm/lib/modules`,
copied into the recovery image by `device.mk`, and `init.qcom.recovery.rc` loads
`xiaomi_tp`, `lct_tp` and `ft3683g_spi` from `/vendor_dlkm/lib/modules` in its
`on fs` action. The other dependencies (`miev`, `hardware_info`,
`lx_charger_class`, `panel_event_notifier`, `spi-msm-geni`, `msm_drm`) are
already in the recovery first-stage list.

The driver asks for `focaltech_ts_fw_sanxing.bin` through `request_firmware`,
which recovery does not carry; it logs the failed request and continues with the
controller's existing firmware, and touch works. The `ft3610_p19a*.ini` files
in the vendor image are not that filename and are not needed in recovery.

The `user` build intentionally removes **Enable ADB**, **Mount/unmount system**
and **Format system** from recovery (`recovery_main.cpp` keeps them for
`userdebug` only). Use a `userdebug` lunch target if those options are needed;
this tree does not weaken a release recovery to add them back.

## Platform repos

**Stock LineageOS 23.2 has no sm6225 platform tree.** There is no
`hardware/qcom-caf/sm6225` and no `device/qcom/sepolicy_vndr/sm6225` in the
LineageOS org, and its bengal devices run the `legacy-um` policy with
`QCOM_HARDWARE_VARIANT := sm8250`. Zephyr's blobs are 5.15-era
(`vendor.qti.hardware.display.composer@3.0`, `android.hardware.audio@7.1`), so
the sm8250 set is not an interface-level match.

The fix ships in this repo: `local_manifests/zephyr.xml`.

```bash
cp device/xiaomi/zephyr/local_manifests/zephyr.xml .repo/local_manifests/
repo sync -c -j8 --force-sync
```

A plain `repo sync` is what applies it: fetches the replacement projects,
deletes the five they replace, and creates the linkfiles the manifest declares.
`repo sync hardware/qcom-caf ...` does *not* work — repo resolves its arguments
as project names or paths, and `hardware/qcom-caf` is a directory, not a
project (`error: project hardware/qcom-caf not found`).

It swaps Lineage's `hardware/qcom-caf/common` — and the five projects that tree
replaces — for the SM6225 platform set (Redmi Note 12 4G: also SM6225, also
Android 16), mirrored into the `uzbforce` org from the `rn124g-development`
forks and pinned to the commits the current build used, and adds:

| Path | Contents |
|---|---|
| `hardware/qcom-caf/common` | fork; `_515` → `sm6225`, pickup files |
| `hardware/qcom-caf/sm6225/audio/{agm,pal,primary-hal}` | audio HAL |
| `hardware/qcom-caf/sm6225/data-ipa-cfg-mgr`, `.../dataipa` | IPA |
| `device/qcom/sepolicy_vndr/sm6225` | platform sepolicy |

`hardware/qcom-caf/sm6225/display` used to be the ninth entry and is **pinned out
again**: its composer, allocator and mapper HALs include the techpack display
headers (`display/drm/sde_drm.h`), which the kernel drop does not ship, so the
display HALs stay the stock blobs and their VINTF fragments come from the vendor
repo (see *Blob list notes*). A checkout that already synced the directory has to
drop the leftovers, otherwise soong still sees modules nothing installs:
`rm -rf hardware/qcom-caf/sm6225/display`.

The platform set is mirrored under `uzbforce` as `android_hardware_qcom-caf_*` and
`android_device_qcom_sepolicy_vndr_sm6225`, named from their manifest path —
`android_<path, / as _>`, which is the LineageOS project name for every platform
tree and fixes the one upstream that does not follow it
(`hardware_qcom-caf_common`). Upstream stays
[`rn124g-development`](https://github.com/orgs/rn124g-development/repositories).
`tools/publish-platform-repos.sh <your-org>` re-mirrors all nine into an org you
control, verifies every pinned SHA landed, and with `--rewrite-manifest`
repoints the manifest's `name=` attributes — the pins are commit SHAs and a
mirror push carries every branch and tag, so they stay valid. If `repo sync`
complains that a `remove-project` names a project that does not exist, delete
that line.

Two things this manifest has to get right, both learned from a real build:

- **It has to namespace the platform dirs.** Lineage's own entry for
  `hardware/qcom-caf/common` links a `soong_namespace` stub into every
  `hardware/qcom-caf/<platform>/Android.bp`. Replacing that entry drops those
  links, soong then parses every platform tree in the default namespace, and the
  build dies in the analysis phase with `module "libexthwplugin" already
  defined` — once per module the platform trees share. The manifest repeats the
  links for every dir 23.2 still has; if upstream adds or drops a platform, that
  list needs the same change.
- **The sm6225 sepolicy needs a patch.** The pinned
  `device/qcom/sepolicy_vndr/sm6225` still sets `BOARD_SYSTEM_EXT_PREBUILT_DIR`
  and `BOARD_PRODUCT_PREBUILT_DIR`, which Android 16 replaced with
  `BOARD_*_SEPOLICY_PREBUILT_DIRS`; `build/make` turns the old names into
  errors, so the product config stops before anything is built. The fix is
  patch 0001 in
  [xiaomi_zephyr_cusrom_patches](https://github.com/uzbforce/xiaomi_zephyr_cusrom_patches) —
  run that repo's `apply.sh` after the first sync, and after any sync that
  touches the file.
- **The other patches are first-build findings**, all recorded in the same
  repo. Its README lists each one and what it fixes; the pattern is always the
  same — a ROM project assumes something the zephyr drop or the Android 16
  toolchain does not provide (a techpack header, a soong namespace import, a
  prebuilt symbol, an init keyword). `apply.sh` applies all of them and reports
  the ones that are already in place.

Alternatively, skip the manifest and let `vendorsetup.sh` patch the stock files
at `breakfast` time. `BoardConfig.mk` also falls back to the legacy-UM policy
with a loud `warning` when `device/qcom/sepolicy_vndr/sm6225/` is missing, so a
plain checkout still configures. It just will not boot: the blobs are 5.15-era
(`composer@3.0`, `audio@7.1`) and the sm8250 interface level does not match.

## Overlays

Xiaomi ships this device's resource overlays as compiled APKs: two on `/vendor`
(`*ResTarget_Vendor.apk`) and a Product tier on `/product`
(`*ResCommon_Sys.apk`). Both partitions belong to the build, so the APKs were
excluded from the blob list and the overlays live in `overlay/` as sources
instead, one module per stock APK, with the same package name, target package,
target name, static flag and priority so each replaces its stock counterpart
one for one.

| Module | Stock source | Target |
|---|---|---|
| `FrameworksResTarget` | `/vendor` RRO | `android` (+ `power_profile.xml`) |
| `WifiResTarget` | `/vendor` RRO | `com.android.wifi.resources` |
| `FrameworksResCommon` | `/product` RRO | `android` |
| `WifiResCommon` | `/product` RRO | `com.android.wifi.resources` |
| `SystemUIResCommon` | `/product` RRO | `com.android.systemui` |
| `SettingsResCommon` | `/product` RRO | `com.android.settings` |
| `TelephonyResCommon` | `/product` RRO | `com.android.phone` (+ `telephony_injection.xml`) |
| `TelecommResCommon` | `/product` RRO | `com.android.server.telecom` |
| `CarrierConfigResCommon` | `/product` RRO | `com.android.carrierconfig` (+ `vendor.xml`) |
| `NfcResCommon` | `/product` RRO | `com.android.nfc` |
| `NcmTetheringResCommon` | `/product` RRO | `com.android.networkstack.tethering` |

They are generated, not written by hand — every value is read out of the stock
APK, which is the only place the vendor's numbers exist:

```bash
./tools/port-overlays.py --dump work/root --aapt2 $(command -v aapt2) \
    --firmware zephyr_global_images_OS3.0.311.0.WBUMIXM_16.0 --verify
```

`--verify` compiles and links each overlay against the framework in the dump,
then diffs the resulting resource table, the XML resources and the manifest
against the stock APK. All eleven match; only the entries listed below differ.
`--list` prints what is ported and what is not, with the reason.

Twenty-eight of the stock entries are dropped because nobody in a Lineage build
would read them: Qualcomm and MIUI framework-res additions
(`config_wifi_batched_scan_supported`, `config_dual_bar`, ...), Qualcomm wifi
fork resources that are not in the AOSP wifi overlayable policy either, HyperOS
Settings strings, and the MIUI OAT paths in `config_defaultPinnerServiceFiles`.
Each one carries its reason in the generated file's header. Five stock overlays
are not ported at all — the empty `FrameworksResCommonQva_Sys`, the
CellBroadcastReceiver RRO (all three of its resources are Xiaomi fork
additions), `MccMncOverlay` and the `SettingsRroDevice*` pair (HyperOS SystemUI
and MIUI Settings resources), and the Google/GMS overlays that go with the
product image. `--list` names them.

## Blob list notes

- 3830 lines, 3633 entries: the bulk `vendor/`, then `system_ext/`,
  `odm/`, `product/`, `system/` (the inherited creek sections and the
  zephyr additions in one file).
- Three of them are VINTF fragments the ROM does **not** generate any more:
  `android.hardware.graphics.mapper-impl-qti-display.xml`,
  `vendor.qti.hardware.display.allocator-service.xml` and
  `vendor.qti.hardware.display.composer-service.xml`. They were dropped when the
  platform built the sm6225 display HALs and had to be listed again after the
  tree was pinned out (`tools/gen-proprietary-files.py` no longer excludes them,
  so a regeneration from a new dump keeps them). The services and libraries
  behind them are stock blobs either way — `vendor/bin/hw/
  vendor.qti.hardware.display.{composer,allocator}-service`,
  `vendor/lib64/libsdmcore.so`, `…/hw/android.hardware.graphics.mapper@4.0-impl-qti-display.so`
  — so without the fragments the vendor manifest would declare no graphics HAL
  at all. `memtrack_qti.xml` stays generated by the platform: memtrack lives in
  `hardware/qcom-caf/common`, not in the sm6225 tree.
- `vendor/bin/toolbox` and `vendor/bin/toybox_vendor` are deliberately absent,
  and the vendor repo does not carry them either: `base_vendor.mk` pulls in
  `shell_and_utilities_vendor`, which requires the platform `toolbox_vendor`
  and `toybox_vendor`, so `/vendor/bin` already gets both binaries and the 181
  applet symlinks that point at them. Listing the stock pair as well made the
  vendor image claim those paths twice and soong refused the build with a
  packaging conflict for every one of the 181.
- `vendor/bin/vndservicemanager` and `vendor/etc/init/vndservicemanager.rc` are
  deliberately absent. `frameworks/native/cmds/servicemanager` builds that
  daemon for this release (`vendor: true`, with its own rc) and the product
  lists it in `PRODUCT_PACKAGES`. A prebuilt that implements `IServiceManager`
  has to match the `libbinder` it links; this one is built from a different
  branch than the `libbinder.so` the tree installs, and it aborted in
  `ServiceManager::listServices` (`CHECK(outList->empty())`). While it was
  installed, `/dev/vndbinder` had no context manager: `memtrack` aborted on
  `addService` and SurfaceFlinger never found the AIDL composer.
- Excluded on purpose: `vendor/build.prop`, `vendor/etc/fs_config_*`, the main
  `vendor/etc/vintf/manifest.xml`, `vendor/etc/vintf/compatibility_matrix.xml`
  (both generated from `DEVICE_MANIFEST_FILE` / `DEVICE_MATRIX_FILE`),
  `vendor/etc/init/hw/*.rc` (shipped by `rootdir/`), `vendor/etc/selinux/*` and
  `vendor/overlay/*.apk`.
- Kernel modules are **not** in the list; they come from the kernel repo into
  `vendor_dlkm` / `system_dlkm`.
- Eight entries carry symlinks, folded into their target with `;SYMLINK=...`
  (extract_utils reads `|` as a hash pin and `;` as an argument, so the earlier
  `|SYMLINK=` form was silently treated as a pinned hash and installed no links
  at all). A bare name in the argument means the link sits next to the target;
  otherwise the value is the link's partition-relative path, which the Adreno
  aliases need because the stock link is one directory up (`vendor/lib/
  libEGL_adreno.so -> egl/libEGL_adreno.so`).
- Symlinks the list cannot express are the ones nothing else needs to: the
  build itself creates `/vendor/odm` and `/vendor/lib/modules ->
  /vendor_dlkm/lib/modules` (`build/make/core/Makefile`), and init creates the
  `vendor/rfs/**` links into `/mnt/vendor/persist` at runtime. The generator
  prints them instead of dropping them silently.

- `vendor/bin/hw/vendor.qti.hardware.display.composer-service` is the stock blob
  with **one instruction changed**: the entry of
  `sdm::HWCDisplayBuiltIn::HandleLargeCompositionHint(bool)` is `ret` instead of
  `sub sp, sp, #0x40`. `CPUHint::Init()` fails on zephyr, leaving `cpu_hint_`
  null; `NeedsLargeCompPerfHint()` returns false on its `if (!cpu_hint_)` check
  before it reads `vendor.display.enable_perf_hint_large_comp_cycle`, the caller
  inverts that to `true`, and the hint path then dereferences the null
  `cpu_hint_` at `+0x58` (`ValidateDisplayInternal` →
  `HandleLargeCompositionHint(bool)+68`). Both property values crash, so the
  property is not a fix. The function only sends CPU perf hints, so skipping it
  costs nothing. `tools/patch-composer-hint.py` re-applies the patch and must be
  re-run after regenerating `vendor/xiaomi/zephyr` from the stock dump; it is
  idempotent and refuses to touch a blob whose bytes moved.

## Known gaps

1. **Kernel integration** — the prebuilt route is wired and verified against the
   firmware; the source route is parked, because Xiaomi's OSS drop
   (`zephyr-w-oss`) has no `techpack/` tree: a kernel built from it ships none of
   the display, GPU, video or audio modules the stock `vendor_dlkm` has (268 of
   them), and the HALs that need the techpack display/audio headers cannot be
   compiled against it either. What is left on the prebuilt route is the first
   boot: whether the 268 modules load in the order the stock lists give, and
   whether every HAL comes up with the module lists as installed.
2. **Platform HAL tree** — resolved by `local_manifests/zephyr.xml` (see
   *Platform repos*) and now built: the sm6225 audio, IPA and display-adjacent
   HALs and the thermal service compile, with the namespace and techpack
   findings recorded as patches. Whether each HAL registers at runtime is the
   remaining question.
3. **SEPolicy** — placeholders only, plus whatever the platform tree supplies.
   The FOD chain is labelled and transitioned (see above):
   `displayfeature` and the Xiaomi display-feature HAL, `touchfeature`, and the
   `/dev/mi_display` node. Both Xiaomi domains are **permissive** because their
   sysfs/ioctl sets are undocumented — tighten them and clear
   `SELINUX_IGNORE_NEVERALLOWS` (true for bring-up) before release. `micharge`,
   `citsensorservice` and the TMS NFC HAL still have no `allow` rules.
4. **Overlays** — ported (see *Overlays*). What is left is runtime
   confirmation: `dumpsys overlay` should list all eleven as enabled after the
   first boot. Any entry the target does not declare is silently ignored by the
   framework, so a missed resource shows up as a config value that stayed at its
   AOSP default rather than as a build error.
5. **Camera** — the four `p19A_*` sensor modules and tuning blobs are included
   and `camera.qcom.so` carries the `libprocessgroup_shim` fixup, but no VINTF
   fragment has been written for the provider beyond the stock blobs.
6. **NFC** — zephyr uses **THN31** with Xiaomi's TMS HAL, not NXP SN100. The
   service is AIDL (self-registering) and the stock vendor ships no NFC VINTF
   fragment, so how the framework picks it up (`ro.hardware.nfc`) is unverified.
7. **`mi_ext` is not built.** Stock super has it; Lineage's fstab mounts it
   `nofail`, so any Xiaomi service expecting it will degrade.
8. **Tap-to-wake** — the panel is a Focaltech FT3683G, whose gesture interface
   is `EV_SYN/SYN_CONFIG` on `/dev/input/event3`, not a sysfs node. The QTI power
   HAL is linked with `libperfmgr-ext-xiaomi`, which sends that event; the old
   `TARGET_TAP_TO_WAKE` sysfs property is no longer used.
9. **32-bit apps and the two 32-bit vendor HALs** — stock is a 64-bit + 32-bit
   device (`ro.zygote=zygote64_32`, `armeabi-v7a` in the abilist) and its vendor
   ships 32-bit `android.hardware.cas@1.2-service` and
   `android.hardware.media.omx@1.0-service`, which this 64-bit-only product
   cannot exec. Both are marked `disabled` in their init rc here (they would
   otherwise crash-loop forever), the OMX entry is dropped from the device
   manifest, and the framework resolves the OMX service with
   `tryGetService()` so its absence cannot block playback. Turning the second
   arch on is not a flag: `TARGET_2ND_ARCH`
   alone makes every vendor Make and Soong module build an arm variant, those
   variants link against the stock blobs, and extract-utils declares every one
   of those `compile_multilib: "64"` — so the build stops on missing
   `.so.toc` files (first one: `libar-pal` for `audio.primary.bengal`). The
   installed kernel uapi headers are the arm64 ones as well, and
   `asm/sigcontext.h` uses `__uint128_t`, so any 32-bit module that includes
   `<signal.h>` with the kernel headers on its include path fails. Doing this
   properly needs arm uapi headers from `headers_install ARCH=arm`, a
   vendor-64-bit policy for both build systems, and the host/device module-name
   resolution that `PRODUCT_PACKAGES` applies to multilib modules audited.
10. **VINTF manifest** — `configs/vintf/manifest.xml` is the stock aggregated
   vendor manifest, entry for entry, so the declared instances are exactly the
   ones Xiaomi shipped. What is *not* verified is that every one of them is
   served: 60 of the 68 have no `interface` line in any stock rc file, which is
   normal for QTI HALs that self-register, but only boot-time `vintf` output
   proves it. Entries that turn out dead should be deleted there, not declared
   elsewhere.

## Credits

Base blob list and structure adapted from
[Saslowki/android_device_xiaomi_creek](https://github.com/Saslowki/android_device_xiaomi_creek)
(branch `sixteen-axion`). Stock firmware supplied by the device owner.

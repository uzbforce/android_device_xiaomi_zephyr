#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Redmi Note 17 4G — zephyr / p19a — SM6225-AF (bengal), HyperOS 3.0.310
#

# Inherit from the proprietary version
include vendor/xiaomi/zephyr/BoardConfigVendor.mk

DEVICE_PATH := device/xiaomi/zephyr

# ---------------------------------------------------------------------------
# Bring-up overrides
# ---------------------------------------------------------------------------
BUILD_BROKEN_DUP_RULES                       := true
BUILD_BROKEN_ELF_PREBUILT_PRODUCT_COPY_FILES := true

# build_image filters every partition image through the per-partition install
# file list (INTERNAL_* IMAGE_FILES). Nine vendor VINTF fragments (health, ir,
# boot@1.2, atrace, sensors, memtrack, wifi hostapd/supplicant, non_qmaa) live
# in the vendor staging tree but are absent from that list, so they were
# silently dropped from vendor.img. Without the health fragment,
# servicemanager rejects android.hardware.health.IHealth/default with
# EX_ILLEGAL_ARGUMENT ("VINTF declaration error"), the HAL aborts, and
# system_server dies in BatteryService -- the device loops on the boot
# animation. Build the images from the whole staging tree instead.
BUILD_BROKEN_INCORRECT_PARTITION_IMAGES      := true
ALLOW_MISSING_DEPENDENCIES                   := true

# Keep this false for release builds; it exists because the SEPolicy for a new
# device is never complete on the first boot.
SELINUX_IGNORE_NEVERALLOWS                   := true

# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------
TARGET_ARCH                  := arm64
TARGET_ARCH_VARIANT          := armv8-a
TARGET_CPU_ABI               := arm64-v8a
TARGET_CPU_ABI2              :=
TARGET_CPU_VARIANT           := cortex-a73
TARGET_CPU_VARIANT_RUNTIME   := cortex-a73

# The device launched on Android 13 and its vendor blobs are API 33, which is
# what stock declares (ro.board.first_api_level=33, ro.board.api_level=33).
# init clamps ro.vendor.api_level to ro.product.first_api_level, so declaring
# the platform release here would claim an API surface the vendor does not have.
BOARD_SHIPPING_API_LEVEL     := 33

TARGET_BOARD_PLATFORM        := bengal
TARGET_BOOTLOADER_BOARD_NAME := bengal
BOARD_USES_QCOM_HARDWARE     := true

# bengal on the 5.15 BSP: selects QCOM_HARDWARE_VARIANT sm6225 and the
# hardware/qcom-caf/sm6225 namespace (see vendorsetup.sh).
TARGET_BOARD_SUFFIX          := _515

# ---------------------------------------------------------------------------
# Kernel
#
# Two routes, selected by ZEPHYR_USE_PREBUILT_KERNEL:
#
#   prebuilt (default)
#     The tree that tools/gen-prebuilt-kernel.py assembles in
#     ZEPHYR_PREBUILT_KERNEL_PATH. Nothing is compiled and the modules stay
#     ABI-identical to the vendor blobs, which is what a first boot wants.
#
#     It is the default because the OSS drop cannot produce a usable kernel for
#     this device: MiCode/Xiaomi_Kernel_OpenSource, branch zephyr-w-oss has no
#     techpack/ tree, and the stock vendor_dlkm ships msm_drm.ko, msm_kgsl.ko,
#     msm_video.ko, msm_vidc*, q6_dlkm.ko, audio_*_dlkm.ko, lpass* and the rest
#     of the display/audio/video modules built from it (268 modules in all).
#     A kernel built from the OSS tree has none of them, so the device would
#     come up without display, GPU, video and audio, and the HALs that include
#     techpack display/audio headers (libqcompostprocbundle's <sound/
#     audio_effects.h>, the sm6225 SDE code's <display/drm/sde_drm.h>) cannot be
#     compiled against it either.
#
#   source
#     kernel/xiaomi/zephyr  <- MiCode/Xiaomi_Kernel_OpenSource, branch
#         zephyr-w-oss, with MiCode/kernel_devicetree (same branch) merged into
#         arch/arm64/boot/dts/vendor. The OSS tree ships the module lists read
#         below: modules.list.msm.zephyr, modules.vendor_blocklist.msm.zephyr,
#         modules.systemdlkm_blocklist.msm.zephyr.
#
#     Keep the source clone in place on both routes: Lineage's generated kernel
#     headers come from `make headers_install` in it.
#
# Verified from the stock boot.img: Linux 5.15.194-android13-8, header v4,
# 4096-byte pages, Image, no ramdisk in boot (the GKI ramdisk is in init_boot).
# ---------------------------------------------------------------------------
ZEPHYR_USE_PREBUILT_KERNEL  ?= true
ZEPHYR_PREBUILT_KERNEL_PATH ?= device/xiaomi/zephyr-kernel

# The uapi headers the HALs compile against come from TARGET_BOARD_KERNEL_HEADERS:
# the qti_kernel_headers / device_kernel_headers modules hand them out
# (libipanat wants <linux/msm_ipa.h>, libgptutils <linux/nfc/nfcinfo.h>, no
# userspace package has either), and build/make/core/config.mk insists the
# directory be called kernel-headers. tools/gen-prebuilt-kernel.py fills it from
# the same 5.15 kernel, so both routes read the same set.
#
# On the source route soong rewrites device_kernel_headers to Lineage's
# generated_kernel_headers (build/soong/cc/cc.go, gated on INLINE_KERNEL_BUILDING,
# which kernel.mk sets), whose genrule runs `make headers_install` in
# TARGET_KERNEL_SOURCE - the reason the source clone has to stay in place next to
# the prebuilt tree even though nothing builds a kernel from it.
TARGET_BOARD_KERNEL_HEADERS := $(ZEPHYR_PREBUILT_KERNEL_PATH)/kernel-headers

# vendor/lineage/build/soong expands the generated_kernel_includes command
# through the lineageVarsPlugin soong namespace, which is registered by
# vendor/lineage/config/BoardConfigSoong.mk. This tree does not include the
# Lineage board config chain, so the namespace was never registered and every
# $(...) in that command expanded to the empty string:
#
#   set -e; if [ -n "" ]; then ... else  -C  O= ARCH=  headers_install; fi
#   ...sbox_command.bash: line 1: -C: command not found
#
# Register the namespace and export the prebuilt header set so the fallback in
# that command can use it.
$(call add_soong_config_namespace,lineageVarsPlugin)
$(eval $(call add_soong_config_var,lineageVarsPlugin,TARGET_BOARD_KERNEL_HEADERS))

# The vendor-partition AIDs (2901-2914) come from the stock image's
# /vendor/etc/{passwd,group}; AOSP only reserves that range and defines none of
# them, so init cannot resolve the groups named by init.qcom.rc until they are in
# the build's database. See configs/config.fs.
TARGET_FS_CONFIG_GEN += $(DEVICE_PATH)/configs/config.fs

TARGET_KERNEL_ARCH           := arm64
TARGET_KERNEL_VERSION        := 5.15
TARGET_KERNEL_HEADER_ARCH    := arm64
TARGET_KERNEL_SOURCE         := kernel/xiaomi/zephyr
TARGET_KERNEL_CONFIG         := gki_defconfig vendor/zephyr_GKI.config
TARGET_KERNEL_VARIANT_CONFIG := vendor/zephyr_consolidate.config
TARGET_KERNEL_CLANG_COMPILE  := true

BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_KERNEL_IMAGE_NAME         := Image
BOARD_KERNEL_PAGESIZE           := 4096
BOARD_KERNEL_BASE               := 0x00000000
BOARD_KERNEL_OFFSET             := 0x00008000
BOARD_RAMDISK_OFFSET            := 0x01000000
BOARD_TAGS_OFFSET               := 0x00000100
BOARD_DTB_OFFSET                := 0x01f00000

BOARD_BOOT_HEADER_VERSION      := 4
BOARD_MKBOOTIMG_ARGS           += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_INIT_BOOT_HEADER_VERSION := 4
BOARD_MKBOOTIMG_INIT_ARGS      += --header_version $(BOARD_INIT_BOOT_HEADER_VERSION)

BOARD_KERNEL_CMDLINE := \
    disable_dma32=on \
    rcu_nocbs=all \
    rcutree.enable_rcu_lazy=1 \
    rcu_normal=1 \
    rcu_expedited=1 \
    kasan=off \
    bootinfo.fingerprint=$(LINEAGE_VERSION) \
    swinfo.fingerprint=$(LINEAGE_VERSION)

# The overlays live in dtbo.img. The base devicetree is not appended to boot:
# with header v4 it is the dtb section of vendor_boot.img, and that is where the
# stock image keeps its 27 concatenated DTBs. BOARD_DTB_OFFSET above is the one
# the stock bootloader expects.
BOARD_KERNEL_SEPARATED_DTBO     := true

# Boot parameters. The stock vendor_boot.img carries exactly these five in its
# bootconfig. androidboot.hardware=qcom is what makes init set ro.hardware, and
# ro.hardware is what decides which /vendor/etc/init/hw/init.<hw>.rc gets
# imported. The first-stage fstab is NOT named after ro.hardware: this
# bootloader passes androidboot.fstab_suffix=default, and fs_mgr looks the
# suffix up in that order (fstab_suffix, hardware, hardware.platform), so
# first-stage mount reads /first_stage_ramdisk/fstab.default.
BOARD_BOOTCONFIG := \
    androidboot.hardware=qcom \
    androidboot.memcg=1 \
    androidboot.usbcontroller=4e00000.dwc3 \
    androidboot.usb.dwc3_msm=4e00000.hsusb \
    androidboot.load_modules_parallel=true

# ---------------------------------------------------------------------------
# Kernel modules
#
# Both routes fill the same BOARD_<PARTITION>_KERNEL_MODULES(_LOAD) variables,
# which the build turns into lib/modules + modules.load on vendor_dlkm,
# system_dlkm and the vendor ramdisk. Only the source of the lists differs: the
# prebuilt tree carries the stock lists verbatim, the OSS kernel carries its own.
# ---------------------------------------------------------------------------
ifeq ($(ZEPHYR_USE_PREBUILT_KERNEL),true)

# BOARD_PREBUILT_DTBOIMAGE is read through a blueprint glob, and soong's glob
# helper panics on a path in another directory tree ("unexpected relative path
# outside directory") - a five-line stack trace that says nothing about the
# cause. The tree therefore has to sit inside the source tree, which is where
# gen-prebuilt-kernel.py puts it by default.
ifneq ($(filter /%,$(ZEPHYR_PREBUILT_KERNEL_PATH)),)
    $(error ZEPHYR_PREBUILT_KERNEL_PATH is absolute ($(ZEPHYR_PREBUILT_KERNEL_PATH)); soong cannot use a prebuilt DTBO image from outside the source tree. Put the kernel tree at device/xiaomi/zephyr-kernel, or pass a path relative to the source root)
endif

ifneq ($(wildcard $(ZEPHYR_PREBUILT_KERNEL_PATH)/kernel),)
    TARGET_PREBUILT_KERNEL   := $(ZEPHYR_PREBUILT_KERNEL_PATH)/kernel
    BOARD_PREBUILT_DTBOIMAGE := $(ZEPHYR_PREBUILT_KERNEL_PATH)/dtbs/dtbo.img

    # The boot image and the vintf kernel check both read the kernel image from
    # $(PRODUCT_OUT)/kernel. Nothing else creates that file: kernel.mk defines
    # its copy rule for $(INSTALLED_KERNEL_TARGET), which is still empty while
    # kernel.mk is being parsed, so the rule is dropped and the build fails with
    # "'out/target/product/zephyr/kernel' ... missing and no known rule to make
    # it". Shipping the image as a copy file named "kernel" is what creates it.
    PRODUCT_COPY_FILES += $(TARGET_PREBUILT_KERNEL):kernel

    # The image is prebuilt, the uapi headers are not: nqnfcinfo, libbt-vendor
    # and libgptutils build against Lineage's generated_kernel_headers, which its
    # soong generator produces by running `make headers_install` in the kernel
    # source (linux/nfc/nfcinfo.h is Qualcomm's and exists nowhere else). So the
    # source tree has to stay in place even on this route - and because it is
    # there, kernel.mk would build the kernel from it, which is what this
    # variable prevents. As a prebuilt kernel this is the route Lineage itself
    # detects; the variable just makes the choice explicit.
    TARGET_FORCE_PREBUILT_KERNEL := true
    # The device ships the stock 5.15 image on purpose: the OSS drop has no
    # techpack, so a source-built kernel would come up without display, GPU,
    # video or audio. Allow it on release builds, where Lineage otherwise
    # rejects TARGET_FORCE_PREBUILT_KERNEL.
    LINEAGE_ALLOW_PREBUILT_KERNEL := true

    # vendor_boot v4 carries the base devicetree in its dtb section. The stock
    # image holds 27 concatenated DTBs; they were split out verbatim into the
    # prebuilt tree, and build/make's rule for BOARD_PREBUILT_DTBIMAGE_DIR is a
    # plain `cat`, so they reproduce the stock blob byte for byte (sha256
    # 39043b94b94c695f6d973c88d3c433a7e71dce1b59c2ef3fb249d513780ba8f5).
    # Without this the built vendor_boot.img has an empty dtb section and the
    # bootloader cannot start Linux from it.
    BOARD_INCLUDE_DTB_IN_BOOTIMG := true
    BOARD_PREBUILT_DTBIMAGE_DIR  := $(ZEPHYR_PREBUILT_KERNEL_PATH)/dtbs/dtb

    BOARD_VENDOR_KERNEL_MODULES := $(wildcard $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_dlkm/*.ko)
    BOARD_VENDOR_KERNEL_MODULES_LOAD := $(strip \
        $(shell cat $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_dlkm/modules.load 2>/dev/null))
    BOARD_VENDOR_KERNEL_MODULES_BLOCKLIST_FILE := \
        $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_dlkm/modules.blocklist

    BOARD_VENDOR_RAMDISK_KERNEL_MODULES := $(wildcard $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_ramdisk/*.ko)
    # Recovery deliberately loads only the stock module list. The panel is a
    # "focaltech,ft3683g" SPI node, so ft3683g_spi is the right driver (not the
    # I2C focaltech_fts, which matches "focaltech,fts_ts" and cannot load: its
    # qts_client_register symbol is not exported). But loading ft3683g_spi in
    # the recovery first stage probes it before /vendor is mounted and panics
    # this kernel: the OEM logo goes black, the BCB stays set, and the
    # bootloader loops back into recovery until the whole stock firmware is
    # flashed. Keep recovery key-only; see README.
    BOARD_VENDOR_RAMDISK_KERNEL_MODULES_LOAD := $(strip \
        $(shell cat $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_ramdisk/modules.load 2>/dev/null))
    BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD := $(strip \
        $(shell cat $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_ramdisk/modules.load.recovery 2>/dev/null))
    BOARD_VENDOR_RAMDISK_KERNEL_MODULES_BLOCKLIST_FILE := \
        $(ZEPHYR_PREBUILT_KERNEL_PATH)/vendor_ramdisk/modules.blocklist

    BOARD_SYSTEM_KERNEL_MODULES := $(shell \
        find $(ZEPHYR_PREBUILT_KERNEL_PATH)/system_dlkm -name '*.ko' 2>/dev/null)
    BOARD_SYSTEM_KERNEL_MODULES_LOAD := $(strip \
        $(shell cat $(ZEPHYR_PREBUILT_KERNEL_PATH)/system_dlkm/modules.load 2>/dev/null))
else
    $(error ZEPHYR_USE_PREBUILT_KERNEL is true but $(ZEPHYR_PREBUILT_KERNEL_PATH)/kernel does not exist - run tools/gen-prebuilt-kernel.py, see README "Kernel")
endif

else

# modules.list.msm.zephyr is the kernel's link-order list: the 102 modules that
# have to be loadable before the dynamic partitions are mounted. They go into
# the vendor ramdisk, which is where the stock build puts them as well (295
# modules there, 102 in modules.load, 296 in modules.load.recovery). A name
# without a .ko next to it is normal - the stock recovery list has one - so the
# build is told to tolerate it instead of failing.
zephyr_kernel_modules := $(strip \
    $(shell cat $(TARGET_KERNEL_SOURCE)/modules.list.msm.zephyr 2>/dev/null))

BOARD_VENDOR_RAMDISK_KERNEL_MODULES_LOAD := $(zephyr_kernel_modules)
BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD := $(zephyr_kernel_modules)
BOARD_VENDOR_KERNEL_MODULES_LOAD := $(zephyr_kernel_modules)
# Everything the kernel builds as a module goes onto vendor_dlkm, so the
# ramdisk only has to carry the ones that are loaded before it is mounted.
BOOT_KERNEL_MODULES := $(zephyr_kernel_modules)

BOARD_VENDOR_KERNEL_MODULES_BLOCKLIST_FILE := \
    $(TARGET_KERNEL_SOURCE)/modules.vendor_blocklist.msm.zephyr
BOARD_VENDOR_RAMDISK_KERNEL_MODULES_BLOCKLIST_FILE := \
    $(BOARD_VENDOR_KERNEL_MODULES_BLOCKLIST_FILE)
BOARD_SYSTEM_KERNEL_MODULES_BLOCKLIST_FILE := \
    $(TARGET_KERNEL_SOURCE)/modules.systemdlkm_blocklist.msm.zephyr

endif

BOARD_KERNEL_MODULES_LOAD_ALLOW_MISSING := true

# ---------------------------------------------------------------------------
# Partition layout — measured from the stock super.img / rawprogram XML
# ---------------------------------------------------------------------------
TARGET_COPY_OUT_ODM           := odm
TARGET_COPY_OUT_VENDOR        := vendor
TARGET_COPY_OUT_PRODUCT       := product
TARGET_COPY_OUT_SYSTEM_EXT    := system_ext
TARGET_COPY_OUT_VENDOR_DLKM   := vendor_dlkm
TARGET_COPY_OUT_SYSTEM_DLKM   := system_dlkm

BOARD_FLASH_BLOCK_SIZE                := 262144
BOARD_BOOTIMAGE_PARTITION_SIZE        := 100663296
# The stock vendor_boot is the same size as boot. Without this the build never
# creates a vendor_boot.img, so the vendor ramdisk (first-stage fstab, module
# lists, bootconfig) would not exist at all.
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_DTBOIMG_PARTITION_SIZE          := 25165824
BOARD_INIT_BOOT_IMAGE_PARTITION_SIZE  := 8388608
BOARD_RECOVERYIMAGE_PARTITION_SIZE    := 104857600

# Stock: 10190061568 byte super, group qti_dynamic_partitions_a.
# Stock partition sizes (odm 2375680, product 3486203904, system 916889600,
# system_dlkm 348160, system_ext 846622720, vendor 729759744,
# vendor_dlkm 20709376) leave ~3.2 GB of headroom; the sizes below add margin
# for a Lineage build while staying inside the group.
BOARD_SUPER_PARTITION_SIZE              := 10190061568
BOARD_SUPER_PARTITION_GROUPS            := qti_dynamic_partitions
BOARD_QTI_DYNAMIC_PARTITIONS_SIZE       := $(shell expr $(BOARD_SUPER_PARTITION_SIZE) - 4194304)
BOARD_SUPER_PARTITION_METADATA_DEVICE   := super
BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST := \
    odm \
    product \
    system \
    system_dlkm \
    system_ext \
    vendor \
    vendor_dlkm

BOARD_ODMIMAGE_PARTITION_SIZE          := 4194304
BOARD_PRODUCTIMAGE_PARTITION_SIZE      := 3758096384
BOARD_SYSTEMIMAGE_PARTITION_SIZE       := 1073741824
BOARD_SYSTEM_DLKMIMAGE_PARTITION_SIZE  := 4194304
BOARD_SYSTEM_EXTIMAGE_PARTITION_SIZE   := 943718400
BOARD_VENDORIMAGE_PARTITION_SIZE       := 838860800
BOARD_VENDOR_DLKMIMAGE_PARTITION_SIZE  := 33554432

# ---------------------------------------------------------------------------
# Filesystems — stock ships EROFS, with ext4 fallbacks in fstab
# ---------------------------------------------------------------------------
ifeq ($(WITH_EROFS),true)
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE         := erofs
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE      := erofs
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE      := erofs
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE     := erofs
BOARD_SYSTEM_EXTIMAGE_FILE_SYSTEM_TYPE  := erofs
BOARD_SYSTEM_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
else
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE         := ext4
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE      := ext4
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE      := ext4
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE     := ext4
BOARD_SYSTEM_EXTIMAGE_FILE_SYSTEM_TYPE  := ext4
BOARD_SYSTEM_DLKMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := ext4
endif

TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true

BOARD_EROFS_PAGESIZE      := 4096
BOARD_EROFS_COMPRESSOR    := lz4
BOARD_EROFS_PCLUSTER_SIZE := 262144
BOARD_RAMDISK_USE_LZ4     := true

# ---------------------------------------------------------------------------
# A/B + virtual A/B (stock super uses virtual_ab_device, metadata v10.2)
# ---------------------------------------------------------------------------
AB_OTA_UPDATER                     := true
BOARD_USES_METADATA_PARTITION      := true
BOARD_VIRTUAL_AB_OTAPREOPT         := true
BOARD_VIRTUAL_AB_COMPRESSION       := true
BOARD_VIRTUAL_AB_COMPRESSION_METHOD := lz4
BOARD_VIRTUAL_AB_COW_VERSION       := 3

AB_OTA_PARTITIONS += \
    boot \
    dtbo \
    init_boot \
    odm \
    product \
    recovery \
    system \
    system_dlkm \
    system_ext \
    vbmeta \
    vbmeta_system \
    vendor \
    vendor_boot \
    vendor_dlkm

# ---------------------------------------------------------------------------
# AVB — stock vbmeta chains boot/recovery/vbmeta_system, SHA256_RSA2048
# ---------------------------------------------------------------------------
BOOT_SECURITY_PATCH   := 2026-05-05
# Reports the vendor SPL of the shipping build. Kept in step with the platform
# SPL override in vendor/lineage/release/flag_values/bp4a/ so Settings does not
# show a months-old vendor patch on a current build.
VENDOR_SECURITY_PATCH := 2026-11-05

BOARD_AVB_ENABLE                 := true
# The top-level vbmeta is signed separately from the chained boot/recovery/
# vbmeta_system images. Without these two lines it falls back to AOSP's public
# testkey while the chained images use the private key.
BOARD_AVB_ALGORITHM              := SHA256_RSA4096
BOARD_AVB_KEY_PATH               := vendor/lineage-priv/keys/avb.pem
BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 3
# The GSI public keys are referenced by fstab's avb_keys before any dynamic
# partition is mounted. Keep them in the vendor ramdisk, not /system.
BOARD_MOVE_GSI_AVB_KEYS_TO_VENDOR_BOOT := true

BOARD_AVB_RECOVERY_ALGORITHM             := SHA256_RSA4096
BOARD_AVB_RECOVERY_KEY_PATH              := vendor/lineage-priv/keys/avb.pem
BOARD_AVB_RECOVERY_ROLLBACK_INDEX        := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_RECOVERY_ROLLBACK_INDEX_LOCATION := 1

BOARD_AVB_DTBO_ALGORITHM             := SHA256_RSA4096
BOARD_AVB_DTBO_KEY_PATH              := vendor/lineage-priv/keys/avb.pem
BOARD_AVB_DTBO_ROLLBACK_INDEX        := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_DTBO_ROLLBACK_INDEX_LOCATION := 3

BOARD_AVB_BOOT_ALGORITHM             := SHA256_RSA4096
BOARD_AVB_BOOT_KEY_PATH              := vendor/lineage-priv/keys/avb.pem
BOARD_AVB_BOOT_ROLLBACK_INDEX        := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_BOOT_ROLLBACK_INDEX_LOCATION := 4

BOARD_AVB_VBMETA_SYSTEM                          := product system system_dlkm system_ext
BOARD_AVB_VBMETA_SYSTEM_ALGORITHM                := SHA256_RSA4096
BOARD_AVB_VBMETA_SYSTEM_KEY_PATH                 := vendor/lineage-priv/keys/avb.pem
BOARD_AVB_VBMETA_SYSTEM_ROLLBACK_INDEX           := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VBMETA_SYSTEM_ROLLBACK_INDEX_LOCATION  := 2

BOARD_AVB_SYSTEM_DLKM_ADD_HASHTREE_FOOTER_ARGS += --hash_algorithm sha256
BOARD_AVB_VENDOR_ADD_HASHTREE_FOOTER_ARGS      += --hash_algorithm sha256
BOARD_AVB_VENDOR_DLKM_ADD_HASHTREE_FOOTER_ARGS += --hash_algorithm sha256
BOARD_AVB_ODM_ADD_HASHTREE_FOOTER_ARGS         += --hash_algorithm sha256

# ---------------------------------------------------------------------------
# SELinux
# ---------------------------------------------------------------------------
# Stock LineageOS 23.2 ships no sm6225 platform policy (its bengal devices use
# the legacy-UM branch). Prefer the sm6225 tree when it is present, and fall
# back so the build still runs on a plain 23.2 checkout.
ifneq ($(wildcard device/qcom/sepolicy_vndr/sm6225/SEPolicy.mk),)
include device/qcom/sepolicy_vndr/sm6225/SEPolicy.mk
else
$(warning device/qcom/sepolicy_vndr/sm6225 is missing - using the legacy-UM policy; vendor HALs will need hand-written rules)
-include device/qcom/sepolicy_vndr/SEPolicy.mk
endif
include device/lineage/sepolicy/libperfmgr/sepolicy.mk

BOARD_VENDOR_SEPOLICY_DIRS       += $(DEVICE_PATH)/sepolicy/vendor
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/private
# Public system_ext policy is the only policy layer both the system_ext and the
# vendor build can see, which is where the QCOM cross-partition property types
# have to live (sepolicy/public/vendor_prop_types.te).
SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS  += $(DEVICE_PATH)/sepolicy/public

# ---------------------------------------------------------------------------
# Soong / HAL config
# ---------------------------------------------------------------------------
$(call soong_config_set, ufsbsg, ufsframework, bsg)
$(call soong_config_set_bool, camera, override_format_from_reserved, true)

# The charger's software switch is /sys/class/qcom-battery/input_suspend and its
# polarity is inverted (0 enables charging, 1 suspends input). Pinning the path
# also skips the HAL's open-probe loop: with no accessible node the loop never
# terminates, so the service never registers and system_server waits 5 s for it
# on every boot.
$(call soong_config_set, lineage_health, charging_control_charging_path, /sys/class/qcom-battery/input_suspend)
$(call soong_config_set, lineage_health, charging_control_charging_enabled, 0)
$(call soong_config_set, lineage_health, charging_control_charging_disabled, 1)

TARGET_PD_SERVICE_ENABLED := true
TARGET_PER_MGR_ENABLED    := true

# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------
TARGET_RECOVERY_FSTAB                      := $(DEVICE_PATH)/rootdir/etc/fstab.qcom
TARGET_RECOVERY_PIXEL_FORMAT               := RGBX_8888
TARGET_RECOVERY_DEVICE_MODULES             := init.qcom.rc
BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE   := true

# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
TARGET_ODM_PROP        += $(DEVICE_PATH)/configs/properties/odm.prop
TARGET_SYSTEM_PROP     += $(DEVICE_PATH)/configs/properties/system.prop
TARGET_VENDOR_PROP     += $(DEVICE_PATH)/configs/properties/vendor.prop
TARGET_PRODUCT_PROP    += $(DEVICE_PATH)/configs/properties/product.prop
TARGET_SYSTEM_EXT_PROP += $(DEVICE_PATH)/configs/properties/system_ext.prop

# ---------------------------------------------------------------------------
# VINTF
# ---------------------------------------------------------------------------
# The 66 per-HAL fragments under vendor/etc/vintf/manifest/ ship as blobs. The
# two aggregated files that the stock image also carries are NOT blobs, because
# the build generates both of these paths itself:
#   vendor/etc/vintf/manifest.xml              <- DEVICE_MANIFEST_FILE
#   vendor/etc/vintf/compatibility_matrix.xml  <- DEVICE_MATRIX_FILE
# configs/vintf/manifest.xml reproduces the stock vendor manifest entry for
# entry (53 HALs, 68 instances), so device registration matches the stock image
# instead of silently dropping everything that lived in the aggregated file.
DEVICE_MANIFEST_FILE := $(DEVICE_PATH)/configs/vintf/manifest.xml

# Only the qcom-caf matrix is listed: it is the framework-facing one, and the
# matching vendor matrix comes from DEVICE_MATRIX_FILE below. There is no
# hardware/xiaomi project in this manifest, so its extra
# xiaomi_framework_compatibility_matrix.xml cannot be referenced here without
# making the build depend on a repo the tree never checks out.
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += \
    hardware/qcom-caf/common/vendor_framework_compatibility_matrix.xml \
    $(DEVICE_PATH)/configs/vintf/framework_compatibility_matrix.xml

DEVICE_MATRIX_FILE += hardware/qcom-caf/common/compatibility_matrix.xml

# ---------------------------------------------------------------------------
# Display / audio / power / radio / wifi
# ---------------------------------------------------------------------------
# 1080x2280 AMOLED, 120 Hz
TARGET_SCREEN_DENSITY    := 420
TARGET_HAS_HDR_DISPLAY   := true
TARGET_HAS_WIDE_COLOR_DISPLAY := true

TARGET_USES_QCOM_MM_AUDIO                      := true
TARGET_PROVIDES_AUDIO_HAL                      := true
AUDIO_FEATURE_ENABLED_DLKM                     := true
AUDIO_FEATURE_ENABLED_AGM_HIDL                 := false
AUDIO_FEATURE_ENABLED_PAL_HIDL                 := false
AUDIO_FEATURE_ENABLED_DTS_EAGLE                := false
AUDIO_FEATURE_ENABLED_GEF_SUPPORT              := true
AUDIO_FEATURE_ENABLED_INSTANCE_ID              := true
AUDIO_FEATURE_ENABLED_PROXY_DEVICE             := true
AUDIO_FEATURE_ENABLED_HW_ACCELERATED_EFFECTS   := true
AUDIO_FEATURE_ENABLED_EXTENDED_COMPRESS_FORMAT := true

# The panel is a Focaltech FT3683G, not a Synaptics TCM, and has no
# in_wakeup_gesture_mode sysfs attribute. Its wake-gesture interface is the
# EV_SYN/SYN_CONFIG input event consumed by ft3683g_spi. The QTI power HAL's
# mode-extension hook lets libperfmgr-ext-xiaomi send that event; the old
# TAP_TO_WAKE_NODE path cannot work on this panel.
$(call soong_config_set,qtipower,mode_ext_lib,//device/xiaomi/zephyr:libperfmgr-ext-xiaomi)

ENABLE_VENDOR_RIL_SERVICE := true

BOARD_WLAN_DEVICE             := qcwcn
BOARD_HOSTAPD_DRIVER          := NL80211
CONFIG_IEEE80211AX            := true
WIFI_DRIVER_STATE_OFF         := "OFF"
WIFI_DRIVER_STATE_ON          := "ON"
WPA_SUPPLICANT_VERSION        := VER_0_8_X
BOARD_HOSTAPD_PRIVATE_LIB     := lib_driver_cmd_$(BOARD_WLAN_DEVICE)
BOARD_WPA_SUPPLICANT_DRIVER   := $(BOARD_HOSTAPD_DRIVER)
WIFI_DRIVER_STATE_CTRL_PARAM  := "/dev/wlan"
WIFI_HIDL_FEATURE_DUAL_INTERFACE := true
BOARD_WPA_SUPPLICANT_PRIVATE_LIB      := $(BOARD_HOSTAPD_PRIVATE_LIB)
BOARD_WPA_SUPPLICANT_PRIVATE_LIB_EVENT := "ON"
WIFI_HIDL_UNIFIED_SUPPLICANT_SERVICE_RC_ENTRY := true

$(shell mkdir -p $(OUT_DIR)/target/product/$(TARGET_DEVICE)/obj/KERNEL_OBJ/usr)

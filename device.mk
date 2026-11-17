#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# NOTE: the PRODUCT_PACKAGES list below is the verified bengal/SM6225 set from
# the creek tree, with the entries that do not apply to zephyr removed. Several
# of these services are also shipped as prebuilts by the vendor repo; where both
# install the same path, the source-built module wins, and the few places that
# would collide on the image were pruned from the blob list instead.
#

# Qualcomm common definitions
$(call inherit-product, hardware/qcom-caf/common/common.mk)

# Emulated storage / virtual A/B
$(call inherit-product, $(SRC_TARGET_DIR)/product/emulated_storage.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/generic_ramdisk.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/android_t_baseline.mk)
PRODUCT_VIRTUAL_AB_COMPRESSION_METHOD := gz

# Dalvik heap for 6 GB of RAM
$(call inherit-product, frameworks/native/build/phone-xhdpi-6144-dalvik-heap.mk)

# Proprietary vendor repo (generated from proprietary-files.txt)
$(call inherit-product, vendor/xiaomi/zephyr/zephyr-vendor.mk)

PRODUCT_AAPT_CONFIG       := normal
PRODUCT_AAPT_PREF_CONFIG  := 420dpi
# The device launched on Android 13, and its vendor blobs are API 33. Declaring
# the platform release (36) made ro.product.first_api_level=36, which also made
# init report ro.vendor.api_level=202504 and told every API check that this is a
# brand-new device. Stock: ro.board.first_api_level=33, ro.board.api_level=33.
PRODUCT_SHIPPING_API_LEVEL := 33
PRODUCT_OTA_ENFORCE_VINTF_KERNEL_REQUIREMENTS := true

# 4 KB pages: BOARD_KERNEL_PAGESIZE is 4096 and every stock blob is aligned
# for it. Without this the Android 16 default (16384) is used and
# check_elf_file rejects the 4 KB-aligned prebuilts such as the compat
# libcrypto-v33 with "Load segment has alignment 4096 but 16384 required".
# 16 KB-aligned binaries still pass, since 16384 % 4096 == 0.
PRODUCT_MAX_PAGE_SIZE_SUPPORTED := 4096

# qti_kernel_headers (the TARGET_BOARD_KERNEL_HEADERS view the HALs compile
# against) used to live in hardware/google/pixel/kernel_headers, whose soong
# namespace had to be listed here. Android 17 moved the module to
# hardware/qcom-caf/common/Android.bp, and that directory declares no
# soong_namespace, so the module sits in the root namespace and needs no
# import. The old namespace no longer exists at all; listing it is what made
# soong abort with "namespace hardware/google/pixel/kernel_headers does not
# exist" once the sm6225 tree was added.

# The QCOM platform trees below declare their own soong_namespace, and nothing
# in this BoardConfig includes hardware/qcom-caf/common/BoardConfigQcom.mk (it
# would also re-pick the kernel and board settings), so the namespaces it would
# normally register never reach soong. The Wi-Fi stack then silently resolves
# to the AOSP fallbacks and the link stage fails:
#
#   module wpa_supplicant missing dependencies: lib_driver_cmd_qcwcn
#   ld.lld: error: undefined symbol: init_wifi_vendor_hal_func_table
#       referenced by frameworks/opt/net/wifi/libwifi_hal/hal_tool.cpp:571
#
# List the same set the qcom-caf board file adds for this platform.
PRODUCT_SOONG_NAMESPACES += \
    hardware/qcom-caf/sm6225 \
    hardware/qcom-caf/bootctrl \
    hardware/qcom-caf/sm6225/data-ipa-cfg-mgr \
    hardware/qcom-caf/thermal \
    hardware/qcom-caf/wlan \
    hardware/qcom-caf/wlan/qcwcn \
    vendor/qcom/opensource/commonsys/display \
    vendor/qcom/opensource/commonsys-intf/display \
    vendor/qcom/opensource/dataservices

# This tree carries its own (empty) soong_namespace in Android.bp, so every
# module defined under it is invisible to the root namespace until the
# directory is imported. Without this line PRODUCT_PACKAGES entries naming
# device-tree modules -- the RROs, libudfpshandler
# -- are silently skipped rather than failing the build, which is why the
# fence shim never reached /vendor/lib64 even though the C2 component store
# blob requires it.
PRODUCT_SOONG_NAMESPACES += device/xiaomi/zephyr

PRODUCT_CHARACTERISTICS := nosdcard

# ---------------------------------------------------------------------------
# Dynamic partitions
# ---------------------------------------------------------------------------
# The stock super partition carries system, system_ext, product, vendor, odm
# and vendor_dlkm as logical partitions -- they are listed in
# BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST in BoardConfig.mk and the fstab
# marks every one of them "logical". Without this flag
# PRODUCT_BUILD_SUPER_PARTITION also evaluates false, and the build then treats
# those six as standalone partitions that do not exist on the device:
#
#   - ro.boot.dynamic_partitions is never set, and recovery_main hides
#     "Advanced -> Enter fastboot" when neither it nor ro.fastbootd.available
#     is true;
#   - an OTA payload targets /dev/block/by-name/system, which is not there, so
#     update_engine_sideload aborts before transferring anything and adb
#     reports "failed to read command".
PRODUCT_USE_DYNAMIC_PARTITIONS := true

# ---------------------------------------------------------------------------
# Partitions / fstab
# ---------------------------------------------------------------------------
# fstab.qcom is installed by rootdir/Android.mk
PRODUCT_PACKAGES += \
    fstab.qcom

# First-stage mount happens before /vendor exists, so the fstab has to be in
# the vendor ramdisk. The name is not fstab.<ro.hardware>: fs_mgr resolves the
# suffix as fstab_suffix, then hardware, then hardware.platform, and this
# bootloader passes androidboot.fstab_suffix=default (visible in
# /proc/bootconfig). A file named fstab.qcom is therefore never opened and
# first-stage mount fails, so the ramdisk copy has to be fstab.default.
PRODUCT_COPY_FILES += \
    device/xiaomi/zephyr/rootdir/etc/fstab.qcom:$(TARGET_COPY_OUT_VENDOR_RAMDISK)/first_stage_ramdisk/fstab.default

# Stock's vendor_boot also carries fstab.emmc for the emmc fstab_suffix. It is
# not the path this bootloader selects (it passes fstab_suffix=default), but the
# file is small and keeps the ramdisk a superset of stock's.
PRODUCT_COPY_FILES += \
    device/xiaomi/zephyr/rootdir/etc/fstab.emmc:$(TARGET_COPY_OUT_VENDOR_RAMDISK)/first_stage_ramdisk/fstab.emmc

# Rootdir init scripts (stock vendor/etc/init/hw, needed because the vendor
# blob list deliberately excludes them)
PRODUCT_PACKAGES += \
    init.qcom.factory.rc \
    init.qcom.rc \
    init.qcom.usb.rc \
    init.qti.kernel.rc \
    init.qti.ufs.rc \
    init.target.rc

# Vendor binder domain manager. base_vendor.mk, which normally pulls this in, is
# not inherited by the product, and the stock prebuilt cannot stand in for it: it
# implements IServiceManager against a different libbinder than the one built
# here and aborts in ServiceManager::listServices before any vendor HAL can
# register on /dev/vndbinder.
PRODUCT_PACKAGES += \
    vndservicemanager

# ---------------------------------------------------------------------------
# A/B
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    otapreopt_script

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.audio@7.1-impl \
    android.hardware.audio.effect@7.0-impl \
    android.hardware.audio.service \
    android.hardware.audio.sounddose-vendor-impl \
    android.hardware.soundtrigger@2.3-impl \
    audio.primary.default \
    audio.r_submix.default \
    audio.usb.default \
    libaudiopreprocessing \
    libbatterylistener \
    libqcomvisualizer \
    libqcomvoiceprocessing \
    libsndcardparser \
    libtinycompress \
    libvolumelistener

# Stock audio policy, except that the BT A2DP output ports are moved out of the
# "primary" module into a "bluetooth" module.
#
# primary is QTI's audio.primary.bengal (PAL), whose A2DP path is the DSP/hardware
# offload encoder behind btaudio_offload_if.so. That encoder session is created by
# QTI's Bluetooth stack, which this build does not ship; the AOSP stack encodes
# SBC/AAC itself and hands PCM to the HAL through IBluetoothAudioProvider. With
# A2DP owned by primary, PAL loops on audio_stream_start()/audio_get_codec_config()
# and AudioFlinger writes into a stream that never reaches the headset.
#
# Declaring the ports under "bluetooth" makes AudioFlinger load
# /vendor/lib64/hw/audio.bluetooth.default.so (BluetoothAudioSession client, FMQ)
# for that device instead. BT SCO deliberately stays in primary: SCO is a real
# PAL front-end and needs no encoder session.
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/audio/audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_policy_configuration.xml

# libqcompostprocbundle is deliberately not built: post_proc includes
# <sound/audio_effects.h>, a techpack/audio uapi header, and the OSS kernel
# drop has no techpack tree at all. The stock lib is in the vendor repo
# (vendor/lib(64)/soundfx/libqcompostprocbundle.so) and is what the stock
# audio HAL next to it expects - it is dlopen'ed through audio_effects.xml, so
# nothing links against it. The platform tree pulls it in on its own
# (audio/primary-hal/configs/audio_vendor_product.mk), which is patch 0001 in
# xiaomi_zephyr_cusrom_patches.

# Bluetooth audio
#
# android.hardware.bluetooth.audio-impl is only a shared library exporting
# createIBluetoothAudioProviderFactory(); the audio HAL is supposed to dlopen it
# and register the factory, and on this tree it never does, so com.android.bluetooth
# blocks forever in BluetoothAudioHalVersionManager::Get() waiting for
# IBluetoothAudioProviderFactory/default and the adapter never finishes enabling.
# android.hardware.bluetooth.audio-service registers it from its own process.
PRODUCT_PACKAGES += \
    android.hardware.bluetooth.audio-impl \
    android.hardware.bluetooth.audio-service \
    android.hardware.bluetooth.audio-V2-ndk.vendor \
    android.hardware.bluetooth@1.0.vendor \
    audio.bluetooth.default \
    libbluetooth_audio_session \
    vendor.qti.hardware.bluetooth.audio-V1-ndk.vendor \
    vendor.qti.hardware.bluetooth_audio@2.1.vendor \
    vendor.qti.hardware.btconfigstore@1.0.vendor \
    vendor.qti.hardware.btconfigstore@2.0.vendor

# ---------------------------------------------------------------------------
# Boot control
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.boot@1.2-impl-qti \
    android.hardware.boot@1.2-impl-qti.recovery \
    android.hardware.boot-service.qti.recovery \
    libutilscallstack.vendor

# ---------------------------------------------------------------------------
# Camera (sensors themselves come from the vendor repo: p19A_* modules)
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.camera.device@3.6.vendor \
    android.hardware.camera.device-V1-ndk.vendor \
    android.hardware.camera.metadata-V1-ndk.vendor \
    android.hardware.camera.provider-V1-ndk.vendor \
    android.hardware.camera.provider@2.4-impl \
    libcamera2ndk_vendor \
    libcamera_metadata.vendor \
    libexif.vendor \
    libgui_vendor \
    libjpeg.vendor \
    libprocessgroup_shim \
    libstdc++_vendor \
    vendor.qti.hardware.camera.device@1.0.service \
    vendor.qti.hardware.camera.device@1.0.vendor \
    vendor.qti.hardware.camera.postproc@1.0.vendor

# ---------------------------------------------------------------------------
# Display / graphics
#
# Only the QSSI side of the graphics stack is compiled here: the composer,
# allocator, gralloc and SDM implementations stay the stock vendor blobs
# (vendor/lib*/hw/android.hardware.graphics.mapper@4.0-impl-qti-display.so,
# libsdmcore.so, libsdmutils.so, ...) that the vendor repo installs. The
# in-tree sm6225 display HAL cannot be built against this kernel source:
# its SDE/DPU code includes the techpack display headers
# (display/drm/sde_drm.h, display/msm/sde_drm.h), and the open source kernel
# tree that kernel/xiaomi/zephyr clones does not ship the techpack, so the
# header flavour and kernel ABI version are unknown. The vendor HAL already
# matches the vendor kernel the phone runs, so building it is pointless.
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.graphics.allocator-V1-ndk.vendor \
    android.hardware.graphics.common-V3-ndk.vendor \
    android.hardware.graphics.composer@2.4.vendor \
    android.hardware.light-V2-ndk.vendor \
    android.hardware.memtrack-V1-ndk.vendor \
    libdisplayconfig.qti \
    libdisplayconfig.system.qti \
    libgralloc.qti \
    libqdMetaData \
    libqdMetaData.system \
    vendor.display.config@1.11.vendor \
    vendor.display.config@1.14 \
    vendor.display.config@2.0 \
    vendor.display.config@2.0.vendor \
    vendor.qti.hardware.display.allocator@1.0.vendor \
    vendor.qti.hardware.display.allocator@3.0.vendor \
    vendor.qti.hardware.display.allocator@4.0.vendor \
    vendor.qti.hardware.display.composer@1.0.vendor \
    vendor.qti.hardware.display.composer@2.0.vendor \
    vendor.qti.hardware.display.composer@3.0.vendor \
    vendor.qti.hardware.display.config-V1-ndk.vendor \
    vendor.qti.hardware.display.config-V2-ndk.vendor \
    vendor.qti.hardware.display.config-V3-ndk.vendor \
    vendor.qti.hardware.display.config-V4-ndk.vendor \
    vendor.qti.hardware.display.config-V5-ndk.vendor \
    vendor.qti.hardware.display.config-V6-ndk.vendor \
    vendor.qti.hardware.display.mapper@1.0.vendor \
    vendor.qti.hardware.display.mapper@1.1.vendor \
    vendor.qti.hardware.display.mapper@2.0.vendor \
    vendor.qti.hardware.display.mapper@3.0.vendor \
    vendor.qti.hardware.display.mapper@4.0.vendor \
    vendor.qti.hardware.display.mapperextensions@1.0.vendor \
    vendor.qti.hardware.display.mapperextensions@1.1.vendor

# ---------------------------------------------------------------------------
# DRM
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.drm-V1-ndk.vendor \
    android.hardware.drm-service.clearkey \
    android.hardware.drm@1.4.vendor \
    libcrypto-v33 \
    libdrm.vendor

# The stock vendor ships the service, its rc and its VINTF fragment too, but the
# platform builds all three and the blob fragment collides with the platform
# module of the same name. Building it also keeps it in step with libdrm.

# ---------------------------------------------------------------------------
# Fingerprint — Goodix FOD, HAL is a vendor prebuilt
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    libudfpshandler

# ---------------------------------------------------------------------------
# Gatekeeper / keymaster / keymint
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.gatekeeper@1.0.vendor \
    android.hardware.keymaster@4.1.vendor \
    android.hardware.security.keymint-V1-ndk.vendor \
    android.hardware.security.keymint-V2-ndk.vendor \
    android.hardware.security.rkp-V3-ndk.vendor \
    android.hardware.security.secureclock-V1-ndk.vendor \
    android.hardware.security.sharedsecret-V1-ndk.vendor \
    libkeymaster_messages.vendor

# ---------------------------------------------------------------------------
# GNSS
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.gnss-V2-ndk.vendor \
    android.hardware.gnss.measurement_corrections@1.1.vendor \
    android.hardware.gnss.visibility_control@1.0.vendor \
    android.hardware.gnss@2.1.vendor

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.health-V1-ndk.vendor \
    android.hardware.health-service.qti_recovery \
    android.hardware.health@2.1.vendor \
    vendor.lineage.health-service.default

# ---------------------------------------------------------------------------
# HIDL plumbing
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hidl.allocator@1.0.vendor \
    android.hidl.base@1.0.vendor \
    libhidltransport.vendor \
    libhwbinder.vendor

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    IFAAService

# ---------------------------------------------------------------------------
# Power / performance
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.power-service-qti \
    vendor.qti.hardware.perf@2.3.vendor \
    vendor.qti.hardware.servicetracker@1.2.vendor

# ---------------------------------------------------------------------------
# Radio / telephony
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.radio-V1-ndk.vendor \
    android.hardware.radio.config-V1-ndk.vendor \
    android.hardware.radio.data-V1-ndk.vendor \
    android.hardware.radio.messaging-V1-ndk.vendor \
    android.hardware.radio.modem-V1-ndk.vendor \
    android.hardware.radio.network-V1-ndk.vendor \
    android.hardware.radio.sim-V1-ndk.vendor \
    android.hardware.radio.voice-V1-ndk.vendor \
    android.hardware.radio@1.6.vendor \
    android.hardware.radio.config@1.3.vendor \
    android.hardware.radio.deprecated@1.0.vendor \
    extphonelib \
    extphonelib-product \
    extphonelib.xml \
    extphonelib_product.xml \
    ims-ext-common \
    ims_ext_common.xml \
    libprotobuf-cpp-full-3.9.1-vendorcompat \
    libprotobuf-cpp-lite-3.9.1-vendorcompat \
    librmnetctl \
    libsqlite.vendor \
    QtiTelephonyCompat \
    qti-telephony-hidl-wrapper \
    qti-telephony-hidl-wrapper-prd \
    qti_telephony_hidl_wrapper.xml \
    qti_telephony_hidl_wrapper_prd.xml \
    qti-telephony-utils \
    qti-telephony-utils-prd \
    qti_telephony_utils.xml \
    qti_telephony_utils_prd.xml \
    telephony-ext \
    xiaomi-telephony-stub

# The stock ATEL UI ready sender never fires on this build, so every incoming
# SMS stays in qcril's power optimisation buffer until it is dropped. Send the
# hook ourselves; see atel-ready/qcom-atel-ready.cpp for the whole story.
PRODUCT_PACKAGES += \
    qcom-atel-ready

# The stock ims.apk keeps its two JNI libraries in its own native library
# directory as symlinks into /system_ext/lib64. ship the real files there so
# System.loadLibrary finds them exactly where the APK expects them; the
# libimscamera_jni/libimsmedia_jni blobs are also installed to /system_ext/lib64.
PRODUCT_COPY_FILES += \
    vendor/xiaomi/zephyr/proprietary/system_ext/lib64/libimscamera_jni.so:$(TARGET_COPY_OUT_SYSTEM_EXT)/lib64/libimscamera_jni.so \
    vendor/xiaomi/zephyr/proprietary/system_ext/lib64/libimsmedia_jni.so:$(TARGET_COPY_OUT_SYSTEM_EXT)/lib64/libimsmedia_jni.so \
    vendor/xiaomi/zephyr/proprietary/system_ext/lib64/libimscamera_jni.so:$(TARGET_COPY_OUT_SYSTEM_EXT)/priv-app/ims/lib/arm64/libimscamera_jni.so \
    vendor/xiaomi/zephyr/proprietary/system_ext/lib64/libimsmedia_jni.so:$(TARGET_COPY_OUT_SYSTEM_EXT)/priv-app/ims/lib/arm64/libimsmedia_jni.so

# QSPA. The stock QTI telephony apps (ims, qcrilmsgtunnel, QtiTelephonyService,
# QtiTelephony) declare
#   android:requiredSystemPropertyName="ro.boot.vendor.qspa.modem"
#   android:requiredSystemPropertyValue="enabled"
# and PackageManager skips any APK whose gate is not met. Stock sets the gate
# from /system_ext/etc/qspa/qspa_default.rc at init, so both rc files ship here;
# without them ImsService never exists and every call falls back to CS, with
# VoLTE/ViLTE/Wi-Fi calling unavailable no matter what the carrier supports.
PRODUCT_COPY_FILES += \
    vendor/xiaomi/zephyr/proprietary/system_ext/etc/init/qspa_system.rc:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/init/qspa_system.rc \
    vendor/xiaomi/zephyr/proprietary/system_ext/etc/qspa/qspa_default.rc:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/qspa/qspa_default.rc

# ---------------------------------------------------------------------------
# Sensors — zephyr ships Xiaomi's citsensorservice + a multihal prebuilt
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.frameworks.sensorservice@1.0.vendor \
    android.hardware.sensors-service.xiaomi-multihal \
    libsensorndkbridge \
    sensors.xiaomi.v2

# ---------------------------------------------------------------------------
# Thermal
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.thermal-service.qti \
    android.hardware.thermal@2.0.vendor

# ---------------------------------------------------------------------------
# USB / vibrator / wifi
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.usb-service.qti

# wpa_supplicant/hostapd come from external/wpa_supplicant_8. The stock Xiaomi
# prebuilts are linked against the firmware's OpenSSL 1.1 (undefined sk_dup)
# while this ROM only ships BoringSSL, so they cannot exec at all: the Wi-Fi
# HAL then has no ISupplicant to talk to (CMD_STA_START_FAILURE) and hostapd is
# missing, which is also why SoftAP/hotspot never shows up. Both prebuilts are
# disabled in proprietary-files.txt.
PRODUCT_PACKAGES += \
    hostapd \
    wpa_supplicant \
    android.hardware.wifi-service \
    android.hardware.wifi.hostapd-V1-ndk.vendor \
    android.hardware.wifi.hostapd@1.0.vendor \
    android.hardware.wifi.supplicant-V1-ndk.vendor \
    libwifi-hal-ctrl \
    libwifi-hal-qcom \
    libwpa_client

PRODUCT_COPY_FILES += \
    frameworks/native/data/etc/android.hardware.wifi.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.wifi.xml \
    frameworks/native/data/etc/android.hardware.wifi.direct.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.wifi.direct.xml \
    frameworks/native/data/etc/android.hardware.bluetooth.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.bluetooth.xml \
    frameworks/native/data/etc/android.hardware.bluetooth_le.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.bluetooth_le.xml

# ---------------------------------------------------------------------------
# Software codec2 / media
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    libavservices_minijail \
    libavservices_minijail.vendor \
    libplatformconfig \
    libsfplugin_ccodec_utils.vendor \
    libstagefright_bufferqueue_helper.vendor \
    libstagefright_foundation.vendor

# Do NOT install the source-built libcodec2_hidl@1.0 / libcodec2_vndk here.
#
# zephyr-vendor.mk already copies the firmware's copies of both to
# $(TARGET_COPY_OUT_VENDOR)/lib64, and extract-files.py patches the stock
# libcodec2_vndk.so with `add_needed('libui_shim.so')` because it still imports
# the pre-Android-14 GraphicBufferMapper::lock/unlock ABI. Asking for the .vendor
# modules too made Soong install a second file over the same destination, and
# the source build (built against the current libui, so it exports the new ABI
# and does not depend on libui_shim) is what ended up in the image.
#
# The QTI Codec2 store (vendor/bin/hw/vendor.qti.media.c2@1.0-service, running as
# media.hwcodec) is a blob linked against the stock library, so losing the old
# ABI there broke every graphics-buffer operation it performs. Symptom: video
# that needs a Surface on the codec failed everywhere while audio (no Surface)
# and stills (no codec) kept working --
#
#   screenrecord: ERROR: unable to create encoder input surface (err=-2147483648)
#   CCodec::createInputSurface() -> CreateCompatibleInputSurface() -> UNKNOWN_ERROR
#   YouTube: thumbnail freezes, never plays
#   Camera: stills fine, switching to video freezes the viewfinder
#
# Keeping the stock (patched) blobs is the arrangement the fixup above assumes,
# so the firmware copies are the only providers of these two paths.

# ---------------------------------------------------------------------------
# Lights
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fastboot / recovery
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.fastboot-service.example_recovery \
    fastbootd

# ---------------------------------------------------------------------------
# Uprev shims required by the vendor blobs on this platform
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    libhidlbase_shim \
    libprotobuf-qccshim \
    libui_shim \
    libui_shim.vendor

# ---------------------------------------------------------------------------
# Vendor copies of platform libraries
#
# The vendor blobs link against libpng, libjsoncpp, libpower and libaudioroute.
# All four build as platform libraries here, so only /system/lib64/lib*.so
# existed and the vendor namespace could not see them: init failed the services
# with "CANNOT LINK EXECUTABLE ... library \"lib*.so\" not found". Asking for
# the .vendor variant installs the same code to /vendor/lib64, where the blobs
# resolve it. health-service.qti (libpng) and the sensors multihal (libpower)
# are on the boot path, so these are not optional.
#
# The IR and vibrator AIDL libraries are not referenced by anything on the
# platform side, so they were never built at all; their blob services
# (android.hardware.ir-service.example,
# vendor.qti.hardware.vibrator.service) need the vendor NDK backend.
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.ir-V1-ndk.vendor \
    android.hardware.vibrator-V2-ndk.vendor \
    libaudioroute.vendor \
    libcurl.vendor \
    libjsoncpp.vendor \
    libpng.vendor \
    libpower.vendor

# ---------------------------------------------------------------------------
# Vibrator
#
# Nothing inherits vendor/qcom/opensource/vibrator/vibrator-vendor-product.mk,
# so vendor.qti.hardware.vibrator.service was never in PRODUCT_PACKAGES and the
# stock binary, rc and vendor.qti.hardware.vibrator.impl.so were what ended up on
# those paths. The stock service aborts against this platform, so the tree builds
# and installs the HAL instead. See the vibrator entry in
# tools/gen-proprietary-files.py.
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    vendor.qti.hardware.vibrator.service

# ---------------------------------------------------------------------------
# OTA
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    update_engine \
    update_engine_sideload \
    update_verifier

# ---------------------------------------------------------------------------
# Resource overlays
#
# Xiaomi ships this device's resource overlays as compiled APKs on /vendor and
# /product, which the build owns; the sources here replace them one for one
# (same package, target, priority). They are generated from those APKs by
# tools/port-overlays.py - regenerate rather than hand-editing.
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    FrameworksResCommon \
    FrameworksResTarget \
    WifiResCommon \
    WifiResTarget \
    SystemUIResCommon \
    SettingsResCommon \
    TelephonyResCommon \
    TelecommResCommon \
    CarrierConfigResCommon \
    NfcResCommon \
    NcmTetheringResCommon

# ---------------------------------------------------------------------------
# Input device configuration for the UDFPS sensor
# ---------------------------------------------------------------------------
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/configs/idc/uinput-goodix.idc:$(TARGET_COPY_OUT_VENDOR)/usr/idc/uinput-goodix.idc \
    $(LOCAL_PATH)/configs/idc/uinput-fpc.idc:$(TARGET_COPY_OUT_VENDOR)/usr/idc/uinput-fpc.idc

# ---------------------------------------------------------------------------
# Fingerprint
#
# The stock HAL is a libhardware driver (hw/fingerprint.goodix_fod.so) wrapped
# in a HIDL 2.1 service. HIDL 2.1 has no onFingerDown(), so UdfpsHelper's cast
# to V2_3 can never succeed and the module never learns a finger is on the
# sensor; the enrollment session then runs into its 60 s timeout and ends in
# FINGERPRINT_ERROR_CANCELED. The AIDL wrapper loads the same libhardware
# module directly and forwards ISession#onPointerDown/Up to the vendor extCmd
# in reserved[0], which is the path MIUI uses. The HIDL service, its .rc and
# its VINTF fragment are therefore no longer shipped (see
# proprietary-files.txt); two HALs would also fight over the TEE.
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    android.hardware.biometrics.fingerprint-service.lineage

PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/configs/init/init.zephyr.fingerprint.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/init.zephyr.fingerprint.rc

# Forces the display large-composition perf hint off after the shipped
# init.qti.display_boot.sh turns it on; that hint crashes the composer HAL. See
# the comment in the file.
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/configs/init/init.zephyr.display.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/init.zephyr.display.rc

# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
# ro.fastbootd.available is what the stock recovery sets (prop.default:71);
# without it, and with ro.boot.dynamic_partitions supplied only by the vendor
# props, recovery_main removes the fastbootd entry from the Advanced menu.
PRODUCT_PROPERTY_OVERRIDES += \
    ro.sf.lcd_density=420 \
    ro.fastbootd.available=true

# Every Xiaomi QTI vendor sets this, and QtiTelephony's PowerUpOptimization is
# gated on it. Setting it is not enough to fix incoming SMS, though: that stock
# app does connect its OEM hook client, but it only sends
# QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS once its own per-slot RIL and IMS bookkeeping
# reports ready, and it never does here ("Not sending ATEL ready: States: [0:
# {true, false, false, false}]"). qcom-atel-ready sends the hook instead.
# It must live in the vendor partition: init rejects persist.vendor.* keys that
# come from /system/build.prop.
PRODUCT_VENDOR_PROPERTIES += \
    persist.vendor.radio.poweron_opt=1

# Privileged permission allowlist for the stock Hotword Enrollment APKs.
# LineageOS enables ro.control_privapp_permissions=enforce, and those two
# Xiaomi-signed /product priv-apps request KEYPHRASE_ENROLLMENT_APPLICATION and
# INTERACT_ACROSS_USERS, which no other fragment in the build covers. Without
# this, system_server throws while reading the package config and restarts
# forever, leaving the device on the boot animation. See the XML for the log.
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/configs/permissions/privapp-permissions-hotwordenrollment.xml:$(TARGET_COPY_OUT_PRODUCT)/etc/permissions/privapp-permissions-hotwordenrollment.xml

# ---------------------------------------------------------------------------
# Mount points for vendor firmware images (blob mount helpers)
# ---------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    vendor_bt_firmware_mountpoint \
    vendor_dsp_mountpoint \
    vendor_firmware_mnt_mountpoint

# A17 treble-labeling gate (BOARD_API_LEVEL >= 202604): PowerOffAlarm.apk is a
# stock system_ext app labeled by the sm6225 vendor seapp_contexts. The known
# split is tracked in sepolicy/tracking_list.yaml rather than rewriting the
# working vendor policy or moving the stock APK off system_ext.
PRODUCT_SELINUX_TREBLE_LABELING_TRACKING_LIST_FILE := device/xiaomi/zephyr/sepolicy/tracking_list.yaml

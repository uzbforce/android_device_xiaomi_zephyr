#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from those products. Most specific first.
#
# Still core_64_bit_only.mk: stock runs zygote64_32, but this tree cannot build
# a 32-bit world yet (the installed kernel uapi headers are arm64-only, and the
# stock vendor blobs are declared 64-bit-only). See the README's known gaps.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)

# Keep adbd authentication off on development builds. This is an unlocked,
# unofficial development build, and the "Allow USB debugging?" dialog lives in
# SystemUI: if the ROM hangs before it comes up there is no way to authorize a
# host, which is exactly when `adb` is needed to find out why. Lineage's
# common.mk turns this into ro.adb.secure=0 in system_ext/build.prop (and
# therefore into the recovery prop.default too).
# Release (user) builds keep the stock ADB authentication so the image looks
# like a production build to safety/attestation checks.
# Must be set before the common config is inherited - common.mk tests it with
# `ifdef` at inherit time.
ifneq ($(TARGET_BUILD_VARIANT),user)
WITH_ADB_INSECURE := true
endif

# Inherit from LineageOS common configuration
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Inherit the hardware configuration for the actual device
$(call inherit-product, device/xiaomi/zephyr/device.mk)

# Google apps. MindTheGapps is the package the LineageOS wiki points Android 16
# users at; vendor/gapps is the same project's inline-build tree, so the OTA
# ships GMS/Play Store/SetupWizard instead of asking for a separate sideload.
$(call inherit-product, vendor/gapps/arm64/arm64-vendor.mk)

# Signing keys, when present
-include vendor/lineage-priv/keys/keys.mk

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
PRODUCT_NAME         := lineage_zephyr
PRODUCT_DEVICE       := zephyr
PRODUCT_MANUFACTURER := Xiaomi
PRODUCT_BRAND        := Redmi
PRODUCT_MODEL        := Redmi Note 17 4G

PRODUCT_SYSTEM_NAME   := zephyr_global
PRODUCT_SYSTEM_DEVICE := zephyr

# Stock images are EROFS
WITH_EROFS := true

PRODUCT_BUILD_PROP_OVERRIDES += \
    BuildDesc="zephyr_global-user 16 BP2A.250605.031.A3 OS3.0.310.0.WBUMIXM release-keys" \
    BuildFingerprint=Redmi/zephyr_global/zephyr:16/BP2A.250605.031.A3/OS3.0.310.0.WBUMIXM:user/release-keys

PRODUCT_GMS_CLIENTID_BASE := android-xiaomi

# ---------------------------------------------------------------------------
# Display: 1080x2280 AMOLED, 120 Hz (verified from the stock DTBs)
# ---------------------------------------------------------------------------
TARGET_SUPPORTED_REFRESH_RATES := 60,90,120

$(call soong_config_set,surfaceflinger,frame_rate_category_high,120)
$(call soong_config_set,surfaceflinger,frame_rate_category_min,60)

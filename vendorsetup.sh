#!/usr/bin/env bash
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# zephyr is bengal on a 5.15 kernel (TARGET_BOARD_SUFFIX := _515), which is not
# what stock LineageOS 23.2 expects: upstream maps bengal to the 4.19 family and
# therefore to QCOM_HARDWARE_VARIANT := sm8250.
#
# There are two supported ways to provide the sm6225 platform tree:
#
#   1. local_manifests/zephyr.xml from this repo, which brings a qcom-caf/common
#      fork that already knows about _515 -> sm6225. Nothing to patch; this
#      script detects it and exits.
#   2. Plain LineageOS qcom-caf/common, patched here so bengal is treated as a
#      5.15 platform and the sm6225 namespaces are used.
#
# Do not run the patch path on top of the forked common tree: its
# QCOM_HARDWARE_VARIANT block is already restructured and the seds would nest.

color="\033[0;32m"
end="\033[0m"

ANDROID_BUILD_TOP="${ANDROID_BUILD_TOP:-$(pwd)}"
QCOM_CAF_COMMON="$ANDROID_BUILD_TOP/hardware/qcom-caf/common"
QCOM_DEFS="$QCOM_CAF_COMMON/qcom_defs.mk"
QCOM_BOARD_CONFIG="$QCOM_CAF_COMMON/BoardConfigQcom.mk"
SEPOLICY_PICKUP="$QCOM_CAF_COMMON/os_pickup_sepolicy_vndr.mk"
SM6225_DIR="$ANDROID_BUILD_TOP/hardware/qcom-caf/sm6225"

echo "----------------------------------------------------"
echo -e "${color}zephyr: checking the qcom-caf platform tree${end}"

if [ ! -d "$QCOM_CAF_COMMON" ]; then
    echo "hardware/qcom-caf/common not found under $ANDROID_BUILD_TOP; nothing to do."
    echo "----------------------------------------------------"
    return 0 2>/dev/null || exit 0
fi

# Either the forked common tree (local_manifests/zephyr.xml) or a previous run
# of this script has already put sm6225 in place. Either way, do not re-patch:
# the seds below would nest another ifeq into the restructured block.
if grep -q 'QCOM_HARDWARE_VARIANT := sm6225' "$QCOM_BOARD_CONFIG" 2>/dev/null; then
    echo "hardware/qcom-caf/common already provides sm6225. Nothing to patch."
    echo "----------------------------------------------------"
    return 0 2>/dev/null || exit 0
fi

echo "Using stock qcom-caf/common: applying the bengal/_515 patches."
echo ""

# --- 1. UM family: move bengal into the 5.15 family ------------------------
if ! grep -q 'UM_5_15_FAMILY += bengal' "$QCOM_DEFS"; then
    sed -i 's/^UM_4_19_FAMILY := kona lito bengal$/UM_4_19_FAMILY := kona lito\nifneq ($(TARGET_BOARD_SUFFIX),_515)\n    UM_4_19_FAMILY += bengal\nendif/' "$QCOM_DEFS"
    sed -i '/^UM_5_15_FAMILY := kalama crow$/a ifeq ($(TARGET_BOARD_SUFFIX),_515)\n    UM_5_15_FAMILY += bengal\nendif' "$QCOM_DEFS"
fi

# --- 2. Hardware variant ---------------------------------------------------
# The data-ipa namespace derives from $(QCOM_HARDWARE_VARIANT), so it follows
# automatically - only the variant assignment needs patching.
sed -i 's/^    QCOM_HARDWARE_VARIANT := sm8550$/    ifeq ($(TARGET_BOARD_SUFFIX),_515)\n        QCOM_HARDWARE_VARIANT := sm6225\n    else\n        QCOM_HARDWARE_VARIANT := sm8550\n    endif/' "$QCOM_BOARD_CONFIG"

# --- 3. sepolicy_vndr pickup ---------------------------------------------
if [ -f "$SEPOLICY_PICKUP" ] && ! grep -q 'sm6225/SEPolicy.mk' "$SEPOLICY_PICKUP"; then
    sed -i 's|^    include device/qcom/sepolicy_vndr/sm8550/SEPolicy.mk$|    ifeq ($(TARGET_BOARD_SUFFIX),_515)\n        include device/qcom/sepolicy_vndr/sm6225/SEPolicy.mk\n    else\n        include device/qcom/sepolicy_vndr/sm8550/SEPolicy.mk\n    endif|' "$SEPOLICY_PICKUP"
fi

# --- 4. Soong namespace for the platform tree ----------------------------
if [ -d "$SM6225_DIR" ]; then
    if [ ! -f "$SM6225_DIR/Android.bp" ]; then
        echo -e "${color}Creating $SM6225_DIR/Android.bp${end}"
        cat << 'EOF' > "$SM6225_DIR/Android.bp"
soong_namespace {
    imports: [
        "vendor/qcom/opensource/commonsys-intf/display",
        "vendor/qcom/opensource/display",
    ],
}
EOF
    fi
else
    echo "warning: $SM6225_DIR does not exist - add local_manifests/zephyr.xml,"
    echo "         otherwise the sm6225 HALs cannot be built."
fi

echo ""
echo -e "${color}done${end}"
echo "----------------------------------------------------"

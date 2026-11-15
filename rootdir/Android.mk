#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)
LOCAL_MODULE       := fstab.qcom
LOCAL_MODULE_TAGS  := optional
LOCAL_SRC_FILES    := etc/fstab.qcom
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_PATH  := $(TARGET_OUT_VENDOR_ETC)
include $(BUILD_PREBUILT)

# Stock vendor/etc/init/hw scripts, shipped from the device tree because the
# blob list excludes them (they are rootdir, not blobs).
define add-init-rc
include $(CLEAR_VARS)
LOCAL_MODULE       := $(1)
LOCAL_MODULE_TAGS  := optional
LOCAL_SRC_FILES    := etc/init/hw/$(1)
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_PATH  := $(TARGET_OUT_VENDOR_ETC)/init/hw
include $(BUILD_PREBUILT)
endef

$(eval $(call add-init-rc,init.qcom.factory.rc))
$(eval $(call add-init-rc,init.qcom.rc))
$(eval $(call add-init-rc,init.qcom.usb.rc))
$(eval $(call add-init-rc,init.qti.kernel.rc))
$(eval $(call add-init-rc,init.qti.ufs.rc))
$(eval $(call add-init-rc,init.target.rc))

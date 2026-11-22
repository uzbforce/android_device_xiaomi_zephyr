/*
 * Copyright (C) 2020 The LineageOS Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <aidl/android/hardware/power/BnPower.h>
#include <android-base/file.h>
#include <android-base/logging.h>

#include <array>
#include <dirent.h>
#include <fcntl.h>
#include <linux/input.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

namespace {
int open_ts_input() {
    int fd = -1;
    DIR *dir = opendir("/dev/input");

    if (dir != NULL) {
        struct dirent *ent;

        while ((ent = readdir(dir)) != NULL) {
            if (ent->d_type == DT_CHR) {
                char absolute_path[PATH_MAX] = {0};
                char name[80] = {0};

                strcpy(absolute_path, "/dev/input/");
                strcat(absolute_path, ent->d_name);

                fd = open(absolute_path, O_RDWR);
                if (ioctl(fd, EVIOCGNAME(sizeof(name) - 1), &name) > 0) {
                    // fts_ts is the Focaltech FT3683G input device on zephyr.
                    // Keep the other names for the shared Lineage extension.
                    if (strcmp(name, "fts") == 0 || strcmp(name, "fts_ts") == 0 ||
                            strcmp(name, "goodix_ts") == 0 ||
                            strcmp(name, "NVTCapacitiveTouchScreen") == 0 ||
                            strcmp(name, "synaptics_tcm") == 0 ||
                            strcmp(name, "Synaptics TCM touchscreen") == 0)
                        break;
                }

                close(fd);
                fd = -1;
            }
        }

        closedir(dir);
    }

    return fd;
}

// The touchfeature HAL talks to the xiaomi_tp driver through this node. Its
// SET_CUR_VALUE ioctl takes a 1 KB int buffer whose payload is [mode, value].
// The kernel log labels the first field touchId, but fts_set_cur_value() gets
// buf[0] as the mode and buf[1] as the value. Mode 14 is
// Touch_Doubletap_Mode; without it fts_ts_suspend() computes gesture_support=0
// and the controller stops reporting double taps.
static constexpr int kTouchModeDoubletap = 14;
static constexpr unsigned long kTouchSetCurValue = 0;

bool set_touch_mode(int mode, int value) {
    int fd = open("/dev/xiaomi-touch", O_RDWR | O_CLOEXEC);
    if (fd == -1) {
        PLOG(ERROR) << "Failed to open /dev/xiaomi-touch";
        return false;
    }

    std::array<int, 256> request{};
    request[0] = mode;
    request[1] = value;

    int rc = ioctl(fd, kTouchSetCurValue, request.data());
    close(fd);
    if (rc == -1) {
        PLOG(ERROR) << "Failed to set touch mode " << mode << " to " << value;
        return false;
    }

    LOG(INFO) << "Touch mode " << mode << " set to " << value;
    return true;
}
}  // anonymous namespace

namespace aidl {
namespace android {
namespace hardware {
namespace power {
namespace impl {

static constexpr int kInputEventWakeupModeOff = 4;
static constexpr int kInputEventWakeupModeOn = 5;

using ::aidl::android::hardware::power::Mode;

bool isDeviceSpecificModeSupported(Mode type, bool* _aidl_return) {
    switch (type) {
        case Mode::DOUBLE_TAP_TO_WAKE:
            *_aidl_return = true;
            return true;
        default:
            return false;
    }
}

bool setDeviceSpecificMode(Mode type, bool enabled) {
    switch (type) {
        case Mode::DOUBLE_TAP_TO_WAKE: {
            // Arm the controller's own double-tap gesture before writing the
            // input event. SYN_CONFIG alone only updates the LCT gesture
            // bitmask; it does not set doubletap_status.
            bool touch_mode_ok = set_touch_mode(kTouchModeDoubletap, enabled);

            int fd = open_ts_input();
            if (fd == -1) {
                LOG(WARNING)
                    << "DT2W won't work because no supported touchscreen input devices were found";
                return false;
            }
            struct input_event ev = {};
            ev.type = EV_SYN;
            ev.code = SYN_CONFIG;
            ev.value = enabled ? kInputEventWakeupModeOn : kInputEventWakeupModeOff;
            ssize_t written = write(fd, &ev, sizeof(ev));
            close(fd);
            if (written != sizeof(ev)) {
                PLOG(ERROR) << "Failed to write DT2W input event";
                return false;
            }
            LOG(INFO) << "DT2W " << (enabled ? "enabled" : "disabled");
            return touch_mode_ok;
        }
        default:
            return false;
    }
}

}  // namespace impl
}  // namespace power
}  // namespace hardware
}  // namespace android
}  // namespace aidl

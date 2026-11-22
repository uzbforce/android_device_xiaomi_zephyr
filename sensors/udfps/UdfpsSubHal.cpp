/*
 * SPDX-FileCopyrightText: The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

#define LOG_TAG "sensors.udfps"

#include <V2_1/SubHal.h>

#include <fcntl.h>
#include <log/log.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace android {
namespace hardware {
namespace sensors {
namespace V2_1 {
namespace implementation {

namespace {

constexpr int32_t kSensorHandle = 1;
constexpr int32_t kSensorType = static_cast<int32_t>(SensorType::DEVICE_PRIVATE_BASE) + 3;
constexpr char kSensorStringType[] = "org.lineageos.sensor.udfps";
constexpr char kTouchDevice[] = "/dev/xiaomi-touch";
constexpr char kFodPressPath[] = "/sys/class/touch/touch_dev/fod_press_status";
constexpr int kTouchModeFod = 10;
constexpr int kTouchFodArmed = 3;
constexpr int kTouchFodReleased = 0;
constexpr int kTouchIoctlSetMode = 0x5400;

// The framework deactivates the one-shot sensor as soon as it receives the
// trigger, but the touch panel and fingerprint HAL still need FOD mode while
// the authentication runs. Keep it armed through the 1 s synthetic AOD
// finger-up, then release it.
constexpr auto kTouchReleaseDelay = std::chrono::milliseconds(1500);

using ::android::hardware::Void;
using ::android::hardware::sensors::V1_0::OperationMode;
using ::android::hardware::sensors::V1_0::RateLevel;
using ::android::hardware::sensors::V1_0::Result;
using ::android::hardware::sensors::V1_0::SensorFlagBits;
using ::android::hardware::sensors::V1_0::SharedMemInfo;
using ::android::hardware::sensors::V2_1::Event;
using ::android::hardware::sensors::V2_1::SensorInfo;

bool setTouchMode(int value) {
    int fd = open(kTouchDevice, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        ALOGE("cannot open %s: %s", kTouchDevice, strerror(errno));
        return false;
    }

    int arg[2] = {kTouchModeFod, value};
    int rc = ioctl(fd, kTouchIoctlSetMode, arg);
    if (rc < 0) {
        ALOGE("touch mode %d=%d failed: %s", kTouchModeFod, value, strerror(errno));
    }
    close(fd);
    return rc == 0;
}

int64_t elapsedRealtimeNano() {
    struct timespec ts = {};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}

}  // namespace

class UdfpsSubHal : public ISensorsSubHal {
  public:
    ~UdfpsSubHal() {
        {
            std::lock_guard<std::mutex> lock(mLock);
            mStop = true;
            mActive = false;
        }
        mCv.notify_all();
        if (mThread.joinable()) {
            mThread.join();
        }
        setTouchMode(kTouchFodReleased);
    }

    Return<Result> setOperationMode(OperationMode mode) override {
        return mode == OperationMode::NORMAL ? Result::OK : Result::BAD_VALUE;
    }

    Return<Result> activate(int32_t sensorHandle, bool enabled) override {
        if (sensorHandle != kSensorHandle) {
            return Result::BAD_VALUE;
        }

        {
            std::lock_guard<std::mutex> lock(mLock);
            if (enabled) {
                if (!mActive) {
                    mActive = true;
                    ++mGeneration;
                }
            } else {
                mActive = false;
            }
        }
        mCv.notify_all();
        return Result::OK;
    }

    Return<Result> batch(int32_t sensorHandle, int64_t /* samplingPeriodNs */,
                         int64_t /* maxReportLatencyNs */) override {
        return sensorHandle == kSensorHandle ? Result::OK : Result::BAD_VALUE;
    }

    Return<Result> flush(int32_t /* sensorHandle */) override {
        return Result::INVALID_OPERATION;
    }

    Return<void> registerDirectChannel(const SharedMemInfo& /* mem */,
                                       registerDirectChannel_cb callback) override {
        callback(Result::INVALID_OPERATION, -1);
        return Void();
    }

    Return<Result> unregisterDirectChannel(int32_t /* channelHandle */) override {
        return Result::INVALID_OPERATION;
    }

    Return<void> configDirectReport(int32_t /* sensorHandle */, int32_t /* channelHandle */,
                                    RateLevel /* rate */,
                                    configDirectReport_cb callback) override {
        callback(Result::INVALID_OPERATION, 0);
        return Void();
    }

    Return<void> getSensorsList_2_1(getSensorsList_2_1_cb callback) override {
        SensorInfo sensor = {};
        sensor.sensorHandle = kSensorHandle;
        sensor.name = "UDFPS Sensor";
        sensor.vendor = "The LineageOS Project";
        sensor.version = 1;
        sensor.type = static_cast<SensorType>(kSensorType);
        sensor.typeAsString = kSensorStringType;
        sensor.maxRange = 1.0f;
        sensor.resolution = 1.0f;
        sensor.power = 0.0f;
        sensor.minDelay = -1;
        sensor.fifoReservedEventCount = 0;
        sensor.fifoMaxEventCount = 0;
        sensor.requiredPermission = "";
        sensor.maxDelay = 0;
        sensor.flags = static_cast<uint32_t>(SensorFlagBits::ONE_SHOT_MODE) |
                       static_cast<uint32_t>(SensorFlagBits::WAKE_UP);

        callback({sensor});
        return Void();
    }

    Return<Result> injectSensorData_2_1(const Event& /* event */) override {
        return Result::INVALID_OPERATION;
    }

    Return<void> debug(const hidl_handle& fd, const hidl_vec<hidl_string>& /* args */) override {
        if (fd.getNativeHandle() == nullptr || fd->numFds < 1) {
            ALOGE("missing fd for debug");
            return Void();
        }

        FILE* out = fdopen(dup(fd->data[0]), "w");
        if (out != nullptr) {
            fprintf(out, "UDFPS Sensor handle=%d type=%s active=%d\n", kSensorHandle,
                    kSensorStringType, mActive.load());
            fclose(out);
        }
        return Void();
    }

    const std::string getName() override { return "UDFPS-SubHAL"; }

    Return<Result> initialize(const sp<IHalProxyCallback>& callback) override {
        {
            std::lock_guard<std::mutex> lock(mLock);
            mCallback = callback;
            if (!mThread.joinable()) {
                mThread = std::thread(&UdfpsSubHal::run, this);
            }
        }
        return Result::OK;
    }

  private:
    bool isActive(uint32_t generation) const {
        return mActive.load() && mGeneration.load() == generation;
    }

    bool armTouchMode(uint32_t generation) {
        while (!mStop.load() && isActive(generation)) {
            if (setTouchMode(kTouchFodArmed)) {
                return true;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }
        return false;
    }

    void releaseTouchModeIfCurrent(uint32_t generation) {
        if (!mStop.load() && mGeneration.load() == generation && !mActive.load()) {
            setTouchMode(kTouchFodReleased);
        }
    }

    void run() {
        while (!mStop.load()) {
            uint32_t generation;
            {
                std::unique_lock<std::mutex> lock(mLock);
                mCv.wait(lock, [this] { return mStop.load() || mActive.load(); });
                if (mStop.load()) {
                    break;
                }
                generation = mGeneration.load();
            }

            if (!armTouchMode(generation)) {
                releaseTouchModeIfCurrent(generation);
                continue;
            }

            ALOGI("armed touch FOD mode, waiting for press");
            int fd = open(kFodPressPath, O_RDONLY | O_CLOEXEC);
            if (fd < 0) {
                ALOGE("cannot open %s: %s", kFodPressPath, strerror(errno));
                releaseTouchModeIfCurrent(generation);
                continue;
            }

            bool pressed = false;
            while (!mStop.load() && isActive(generation)) {
                char buf[8] = {};
                lseek(fd, 0, SEEK_SET);
                int len = read(fd, buf, sizeof(buf) - 1);
                if (len > 0 && buf[0] == '1') {
                    if (mCallback == nullptr) {
                        ALOGE("no sensor callback for UDFPS trigger");
                        break;
                    }

                    Event event = {};
                    event.timestamp = elapsedRealtimeNano();
                    event.sensorHandle = kSensorHandle;
                    event.sensorType = static_cast<SensorType>(kSensorType);
                    event.u.data[0] = 1.0f;

                    auto wakelock = mCallback->createScopedWakelock(true);
                    mCallback->postEvents({event}, std::move(wakelock));
                    ALOGI("UDFPS press triggered");
                    pressed = true;
                    break;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }

            close(fd);

            if (!pressed) {
                // The sensor was deactivated before a press; no scan to protect.
                releaseTouchModeIfCurrent(generation);
                continue;
            }

            // Mark the one-shot handled. The framework may already have called
            // activate(false); in either case no more events are expected for this
            // generation. Do not release the touch mode until the scan finishes.
            {
                std::lock_guard<std::mutex> lock(mLock);
                if (mGeneration.load() == generation) {
                    mActive = false;
                }
            }
            mCv.notify_all();

            const auto deadline = std::chrono::steady_clock::now() + kTouchReleaseDelay;
            {
                std::unique_lock<std::mutex> lock(mLock);
                mCv.wait_until(lock, deadline, [this, generation] {
                    return mStop.load() || mGeneration.load() != generation || mActive.load();
                });
            }

            // A new generation means a new activation took ownership of the touch
            // mode while this scan was winding down; leave it armed for that scan.
            releaseTouchModeIfCurrent(generation);
        }

        setTouchMode(kTouchFodReleased);
    }

    sp<IHalProxyCallback> mCallback;
    std::mutex mLock;
    std::condition_variable mCv;
    std::thread mThread;
    std::atomic<bool> mActive{false};
    std::atomic<bool> mStop{false};
    std::atomic<uint32_t> mGeneration{0};
};

}  // namespace implementation
}  // namespace V2_1
}  // namespace sensors
}  // namespace hardware
}  // namespace android

using ::android::hardware::sensors::V2_1::implementation::ISensorsSubHal;
using ::android::hardware::sensors::V2_1::implementation::UdfpsSubHal;

extern "C" ISensorsSubHal* sensorsHalGetSubHal_2_1(uint32_t* version) {
    static UdfpsSubHal subHal;
    *version = SUB_HAL_2_1_VERSION;
    return &subHal;
}

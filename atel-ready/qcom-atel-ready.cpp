/*
 * qcom-atel-ready: tell qcril that the telephony UI is ready ("ATEL UI ready").
 *
 * qcril's power optimisation buffers every incoming SMS behind a cached flag
 * that only the QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS OEM hook sets. Until the flag
 * is set, each message sits in
 * qcril_qmi_sms_update_mt_sms_with_ack_needed_power_opt_buffer for about 20 s
 * and is then dropped without being acknowledged, so the network keeps retrying
 * and eventually gives up. Outgoing SMS is unaffected, which is why this shows
 * up as "can send but cannot receive".
 *
 * Stock firmware sends the hook from QtiTelephony's PowerUpOptimization. That
 * app does connect its OEM hook client here, but it only sends once its own
 * per-slot RIL and IMS bookkeeping reports ready, and on this build it never
 * does: it logs "Not sending ATEL ready: States: [0: {true, false, false,
 * false}]" and stays silent. Send the request ourselves instead. It is a raw
 * AIDL call on IQtiOemHook::oemHookRawRequest, so no QTI interface library is
 * needed.
 */

#define LOG_TAG "qcom-atel-ready"

#include <binder/IBinder.h>
#include <binder/IServiceManager.h>
#include <binder/Parcel.h>
#include <binder/ProcessState.h>
#include <log/log.h>
#include <string.h>
#include <unistd.h>
#include <utils/String8.h>

using namespace android;

namespace {

// The AIDL service is registered with servicemanager under its descriptor plus
// one instance per SIM slot.
constexpr const char* kDescriptor = "vendor.qti.hardware.radio.qcrilhook.IQtiOemHook";

// From IQtiOemHook.Stub: TRANSACTION_setCallback is 1, oemHookRawRequest is 2.
constexpr uint32_t kOemHookRawRequest = 2;

// QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS, with 1 meaning "UI ready". QCRIL moved
// this hook between releases; 0x8001A is the value in the qcril shipped here,
// while 0x8000A is the older published value. Send both: the unknown one is
// ignored, and this removes a silent off-by-one failure mode.
constexpr int32_t kSetAtelUiStatusIds[] = {0x8001A, 0x8000A};

// Every QOEMHOOK request is framed as magic, request id, payload length, payload.
constexpr size_t kPayloadSize = 8 + 4 + 4 + 1;

bool sendRequest(const char* instance, int32_t requestId) {
    sp<IServiceManager> serviceManager = defaultServiceManager();
    if (serviceManager == nullptr) {
        ALOGW("no servicemanager");
        return false;
    }

    // checkService() returns immediately when qcrild has not published this
    // slot yet; getService() would block for five seconds on every retry.
    sp<IBinder> hook = serviceManager->checkService(
            String16(String8::format("%s/%s", kDescriptor, instance)));
    if (hook == nullptr) {
        // qcrild has not published this slot yet; the caller retries.
        return false;
    }

    uint8_t payload[kPayloadSize] = {};
    int32_t length = 1;
    memcpy(payload, "QOEMHOOK", 8);
    memcpy(payload + 8, &requestId, sizeof(requestId));
    memcpy(payload + 12, &length, sizeof(length));
    payload[16] = 1;

    // Same parcel the AIDL proxy builds: interface token, request serial, then
    // the request as a byte array.
    Parcel data;
    status_t status = data.writeInterfaceToken(String16(kDescriptor));
    if (status != OK) return false;
    status = data.writeInt32(0);
    if (status != OK) return false;
    status = data.writeByteArray(kPayloadSize, payload);
    if (status != OK) return false;

    status = hook->transact(kOemHookRawRequest, data, nullptr, IBinder::FLAG_ONEWAY);
    if (status != OK) {
        ALOGW("%s: oemHookRawRequest(%x) failed: %d", instance,
              static_cast<unsigned int>(requestId), status);
        return false;
    }
    return true;
}

bool sendAtelReady(const char* instance) {
    bool ok = true;
    for (size_t i = 0; i < sizeof(kSetAtelUiStatusIds) / sizeof(kSetAtelUiStatusIds[0]); ++i) {
        ok = sendRequest(instance, kSetAtelUiStatusIds[i]) && ok;
    }
    return ok;
}

}  // namespace

int main(int, char**) {
    // Log before touching binder: if the driver setup aborts, this line is the
    // only evidence in logcat that the service was actually executed.
    ALOGI("starting");

    // qcrild registers the qcrilhook AIDL service with the system servicemanager
    // (see vendor_service_contexts), not vndservicemanager. This helper is built
    // for system_ext so it links the system libbinder; select /dev/binder to
    // match that servicemanager before the first lookup.
    sp<ProcessState> processState = ProcessState::initWithDriver("/dev/binder");
    if (processState == nullptr) {
        ALOGE("initWithDriver(/dev/binder) failed");
        return 1;
    }

    const char* instances[] = {"oemhook0", "oemhook1"};
    ALOGI("starting; waiting for qcrilhook instances");
    constexpr int kInstanceCount = sizeof(instances) / sizeof(instances[0]);
    bool sent[kInstanceCount] = {};

    // qcrild publishes the hook only once the modem and QMI are up, which can
    // take a while after boot_completed, and right after a restart it may still
    // expose the old instance. Poll for up to three minutes.
    constexpr int kAttempts = 180;
    for (int attempt = 0; attempt < kAttempts; ++attempt) {
        bool pending = false;
        for (int i = 0; i < kInstanceCount; ++i) {
            if (sent[i]) continue;
            sent[i] = sendAtelReady(instances[i]);
            if (sent[i]) ALOGI("%s: ATEL UI ready sent", instances[i]);
            pending |= !sent[i];
        }
        if (!pending) break;
        sleep(1);
    }

    // qcril can ignore a request that arrives just as the hook registers, and a
    // one-way call gives no acknowledgement, so send it again once it settled.
    sleep(5);
    for (int i = 0; i < kInstanceCount; ++i) {
        if (!sent[i]) {
            ALOGW("%s: never appeared in servicemanager", instances[i]);
        } else if (sendAtelReady(instances[i])) {
            ALOGI("%s: ATEL UI ready sent", instances[i]);
        }
    }

    // The modem can still be bringing its SMS path up when the first call is
    // accepted; one more pass a little later covers that without keeping a
    // daemon alive. qcrild restarts restart this service again from its rc.
    sleep(30);
    for (int i = 0; i < kInstanceCount; ++i) {
        if (sent[i]) sendAtelReady(instances[i]);
    }

    return 0;
}

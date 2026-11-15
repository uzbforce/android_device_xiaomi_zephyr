/*
 * Copyright (C) 2026 The LineageOS Project
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#define LOG_TAG "BtAudioAIDLService"

#include <android/binder_process.h>
#include <log/log.h>

/*
 * android.hardware.bluetooth.audio-impl is a shared library, not a service:
 * hardware/interfaces/bluetooth/audio/aidl/default/service.cpp only exports
 * createIBluetoothAudioProviderFactory(). It is normally loaded by the audio
 * HAL from the optionalInterfaceSharedLibs list in
 * hardware/interfaces/audio/common/all-versions/default/service/service.cpp.
 *
 * That never happens on zephyr: the factory is absent from servicemanager, so
 * com.android.bluetooth blocks in
 * BluetoothAudioHalVersionManager::Get() ->
 * AServiceManager_waitForService("...IBluetoothAudioProviderFactory/default")
 * and the adapter never leaves TURNING_ON, which is why Settings shows
 * Bluetooth switching itself on and off and never scans. Registering the
 * factory from this process is what AOSP wants anyway - see the
 * "bluetooth audio should be in its own process" TODO in
 * hardware/interfaces/audio/aidl/default/bluetooth/ModuleBluetooth.cpp.
 */

extern "C" binder_status_t createIBluetoothAudioProviderFactory();

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(0);

    binder_status_t status = createIBluetoothAudioProviderFactory();
    if (status != STATUS_OK) {
        ALOGE("Could not register IBluetoothAudioProviderFactory/default: %d", status);
        return 1;
    }

    ALOGI("Registered IBluetoothAudioProviderFactory/default");
    ABinderProcess_joinThreadPool();
    return 0;  // should not reach
}

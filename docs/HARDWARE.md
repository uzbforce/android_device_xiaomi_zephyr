# Redmi Note 17 4G (zephyr / p19a) — verified hardware inventory

Everything below was read out of the stock fastboot package
`zephyr_global_images_OS3.0.310.0.WBUMIXM_16.0` (HyperOS 3.0.310.0.WBUMIXM,
Android 16 / SDK 36, `ro.product.first_api_level=36`), not from spec sheets.

Reproduce with `tools/extract-firmware.sh`.

## Identity

| Field | Value | Source |
|---|---|---|
| Device codename | `zephyr` | `odm/etc/boardid_property/*.prop`, `odm/etc/build.prop` |
| Xiaomi project (internal) | `p19a` | `odm/etc/p19a_build.prop`, panel names, camera modules |
| Marketing name | Redmi Note 17 (4G) | `ro.product.odm.marketname` |
| Build fingerprint | `Redmi/zephyr_global/zephyr:16/BP2A.250605.031.A3/OS3.0.310.0.WBUMIXM:user/release-keys` | `odm/etc/p19a_build.prop` |
| Vendor build | `Xiaomi/mivendor_sm6225_global/mivendor:16/...` | `vendor/build.prop` |

`ro.vendor.build.fingerprint` pointing at **mivendor_sm6225_global** is the single most
useful fact here: the vendor image is a **shared SM6225 vendor build**, not a
per-device one. That is why an existing SM6225 tree's blob list transfers well.

### SKUs (`odm/etc/*_build.prop`)

| SKU | Model | Brand | NFC |
|---|---|---|---|
| `p19a` | 26012RN62A | Redmi | no |
| `p19al` | 26012RN62L | Redmi | no |
| `p19ae` | 26012RN62Y | Redmi (`zephyr_n_global`) | yes |
| `p19ap` | 26012PC62G | POCO (`zephyr_p_global`) | yes |

NFC capability comes from `odm/etc/permissions/sku_p19ae/` and `sku_p19ap/`
(`android.hardware.nfc.xml`, `com.nxp.mifare.xml`, `android.hardware.se.omapi.uicc.xml`).
A single tree can cover all four by keeping the SKU dirs.

## SoC / platform

- `ro.board.platform=bengal`, `ro.soc.manufacturer=QTI`, `ro.hardware.egl=adreno`, `ro.hardware.vulkan=adreno`
- Snapdragon 6s 4G Gen 2 (SM6225-AF), Adreno 702 per the stock image; the booted kernel reports `Adreno610v2` via kgsl
- `TARGET_BOARD_PLATFORM := bengal`, `TARGET_BOOTLOADER_BOARD_NAME := bengal`
- DT `qcom,msm-id = <0x206 0x10000>` on the p19a overlays (0x24a/0x249 variants also present)
- UFS 2.2 (`ufshc_mem`, `qcom,ufs-phy-qmp-*`), LPDDR4X
- WLAN/BT: `ro.hardware.wlan.chip=wcn3950`, `ro.hardware.wlan.vendor=qcom` (WCN3950 combo)

## Kernel

```
Linux version 5.15.194-android13-8-00015-gf5526d1116e5-ab15004895
```
Extracted from `boot.img` (header v4, 4096-byte page, 45.5 MB `Image`, no ramdisk in
boot; ramdisk lives in `init_boot.img`). Matches the 5.15.194 sublevel in the OSS
kernel request, and matches HyperOS 3.0.305/310 on other SM6225 devices.

- 268 kernel modules in `vendor_dlkm/lib/modules/`, 19 in `system_dlkm/lib/modules/5.15.194/`
- Device-specific modules of note: `synaptics_tcm_ts.ko`, `focaltech_fts.ko`,
  `bq25960_charger.ko`, `bq25960h_charger.ko`, `sc853x_charger.ko`, `byp_charger.ko`,
  `lx_charger_class.ko`, `qti_battery_charger.ko`, `camera.ko`, `wcd937x_dlkm.ko`
- → **A prebuilt-kernel tree (kernel + dtbo + dlkms) is viable for first bring-up.**
  Do not wait for Xiaomi to publish `zephyr` OSS source.

## Partitions

A/B with virtual A/B (`virtual_ab_device`, metadata v10.2), super group
`qti_dynamic_partitions_a`:

```
odm_a 2.3 MB | product_a 3.49 GB | system_a 917 MB | system_ext_a 847 MB
vendor_a 730 MB | vendor_dlkm_a 21 MB | system_dlkm_a 348 KB | mi_ext_a 1.0 GB
```

All payload partitions are **EROFS** (magic `e2e1f5e0` @ 0x400); fstab lists ext4
fallbacks. `mi_ext` mounts at `/mnt/vendor/mi_ext` and is bind-mounted to `/mi_ext`,
`nofail`.

`vendor/etc/fstab.default` is the authoritative fstab — copy it into the tree's
`rootdir/` and strip the ext4 duplicate lines for a Lineage tree.

## Display

- **1080 × 2280, 120 Hz, AMOLED** (panel timings in the DTB: width `0x438` = 1080,
  height `0x8e8` = 2280, framerate 120)
- Xiaomi panel families in the DTB:
  `qcom,mdss_dsi_p19a_38_0e_0a_{video_dphy,mp_video_dphy,p11,p20,new_p10,new_p11,new_p20}`,
  `qcom,mdss_dsi_p19a_41_02_0b_video_dphy`, `qcom,mdss_dsi_p19a_virtual_video_dphy` (debug)
- Panel calibration: `vendor/etc/qdcm_calib_data_p19a_0e_0a_video_dphy.xml` (911 KB)
  and `odm/etc/mdss_dsi_p19a_*_mi.xml` (17 KB each, Xiaomi colour/feature trees)
- `vendor.xiaomi.hardware.displayfeature@1.0-service` + `vendor.display.color@1.0-service`
- No panel driver work is needed: the panel nodes are **already in zephyr's own dtbo**.
  This is the piece that would otherwise have been borrowed from sapphire — it isn't needed.

## Touch

Dual-sourced, both drivers ship in `vendor_dlkm`:

- **Synaptics TCM** — `synaptics_tcm_ts.ko`, 42 `synaptics,tcm-i2c` references in the DTA
- **FocalTech** — `focaltech_fts.ko`, `focaltech,ft3683g` node, `vendor/firmware/ft3610_p19a{,2,3,4,5}.ini`

Also `vendor.xiaomi.hardware.touchfeature@1.0-service` (game-mode / edge suppression),
`vendor/lib/sensors.touch.detect.so`, `configs/idc/uinput-{fpc,goodix}.idc`.

Tree needs **both** `synaptics_tcm_ts` and `focaltech_fts` in the prebuilt modules —
they are already in the stock `vendor_dlkm`, so shipping the stock `vendor_dlkm`
image covers it.

## Fingerprint

- **Goodix under-display (FOD)**
  - `vendor/firmware/goodix_firmware.bin`, `goodix_cfg_group.bin`
  - `vendor/lib64/hw/fingerprint.goodix_fod.so`, `fingerprint.fpc_fod.so` (fpc is the
    generic fallback present in every mivendor image)
  - `vendor/app/goodix_sz/goodix_sz.apk`
  - `vendor.xiaomi.hardware.fingerprintextension@1.0.so`
  - HAL: `android.hardware.biometrics.fingerprint@2.1-service-lx`
- FOD geometry (props, worth copying verbatim):
  ```
  ro.hardware.fp.fod=true
  ro.hardware.fp.fod.location=low
  persist.vendor.sys.fp.fod.location.X_Y=451,2109
  persist.vendor.sys.fp.fod.size.width_height=178,178
  ro.hardware.fp.fod.lowlight.lux.threshold=3
  ro.hardware.fp.fod.lowlight.brightness.threshold=411
  ```
- DT node `fingerprint_xiaomi` (`compatible = "xiaomi,xiaomi-fp"`), IRQ GPIO 0x53,
  power GPIO 0x6c — present in zephyr's dtbo.

## NFC

- Chip: **THN31** (not NXP SN100 — the SN100/SN220 libs in `vendor/` are the generic
  mivendor payload and are unused here)
  - `vendor/lib64/nfc_nci.thn31nfc.tms.so`
  - `vendor/etc/init/init.thn31.nfc.rc`, `vendor/etc/init/nfc-service-tms.rc`
  - `vendor/etc/SEC_THN31_FW_VTP.txt.bin`, `SEC_THN31F_FW_VTP.txt.bin`
  - `vendor/etc/libnfc-tms_thn31f.conf`, `libnfc-tms.conf`
- HAL: `android.hardware.nfc-service-tms` (`NCI_HAL_MODULE="nfc_nci.tmsnfc"`),
  libs `vendor.tms.tmsnfc@1.0.so`, `vendor.tms.tmsnfc_aidl-V1-ndk.so`
- I2C node in DT: `qcom,nq-*` (irq/ven/clkreq/firm) — standard NQ layout, THN31 is
  wired to the NQ-compatible bus.
- NFC present on `p19ae` / `p19ap` only; gate it with the SKU permissions dirs.

## Cameras

Four sensor modules (dual-sourced front and back):

| Position | Module | Sensor |
|---|---|---|
| Main | `ofilm_ov50d40_main_ii` | OmniVision **OV50D40** (50 MP) |
| Main | `sunny_s5kjnssq33_main_i` | Samsung **S5KJNSSQ33** |
| Front | `ofilm_sc1620cs_front_i` | SmartSens **SC1620CS** |
| Front | `sunny_gc16b3_front_ii` | GalaxyCore **GC16B3** |

Evidence: `vendor/lib64/camera/com.qti.{sensor,sensormodule}.p19A_*.so/.bin`,
`vendor/lib/camera/com.qti.tuned.*p19A_*`, tuning XMLs in `vendor/etc/camera/`.

- Camera HAL: `android.hardware.camera.provider@2.4-service_64`
- Flash: `com.qti.flash.lm3644.so`; EEPROM: `com.qti.eeprom.{irs2381c_polar,truly_cmb433}.so`
- `vendor/etc/camera/model/` ships AI models (preview cache/policy) — large, optional
  for a first boot but needed for stock camera quality.

Camera is the biggest "just works / doesn't work" variable on a new tree: the sensor
`.so`/`.bin` are per-device, so they must come from **this** dump, not creek's.

## Audio

- Codec: **WCD937x** (`wcd937x_dlkm.ko`, `wcd937x_slave_dlkm.ko`, `wcd_core_dlkm.ko`)
- Smart PA 1: `ocs,oca72xxx_pa` at I2C `0x58`, reset GPIO 0x44
- Smart PA 2: `foursemi,fs1815` at I2C `0x34`
- `vendor.xiaomi.hardware.misys@1.0-service` (Xiaomi audio effects),
  `vendor/etc/audio_policy_engine_configuration_mi.xml`,
  `odm/etc/audio_policy_engine_*`.

## Charging / power

- Sub-PMIC: `xiaomi,subpmic-sc6601`
- Charge pumps: `bq25960` / `bq25960h`, `sc853x`, `byp_charger`
- `vendor.xiaomi.hardware.micharge@1.0-service`, `vendor.xiaomi.hardware.batteryantiaging-service`
- Battery algorithm config: `odm/etc/charger/BAA_config_zephyr.json` (+ `_common`)
- `vendor.hal-batteryinfo` / `libhal-batteryinfo.so`, `libbatterylistener.so`

## Sensors

From `vendor/etc/sensors/config/sensor_devinfo.json` + per-sensor JSON:

| Type | Part |
|---|---|
| Accelerometer | STK83xx **or** BMA5 (dual-source) |
| ALS/proximity | STK6A2X **or** SiP1328 |
| Magnetometer | MMC56x3x **or** QMC630x |
| SAR | Semtech SX937x |

HAL: `android.hardware.sensors@2.1-service.multihal`,
`vendor/lib/sensors.ssc.so`, `vendor.xiaomi.sensor.citsensorservice` (odm).

## Misc

- `ro.product.first_api_level=36`, `ro.hardware.keystore_desede=true`,
  `ro.hardware.egl=adreno`
- Security patch level in image: `2026-05-05`
- `avb` enabled everywhere; bootloader unlock required for any of this to boot
- `aboot`/`xbl` chain is SM6225 `bengal`; `vbmeta` flags in the package disables
  verification on flash (`--disable-verity --disable-verification`)

## What this means for the base-tree decision

Measured by checking every entry of each candidate's `proprietary-files.txt`
against the extracted dump:

| Base | Entries | Present in zephyr dump | Coverage |
|---|---|---|---|
| `creek` (Redmi 15 4G, `sixteen-axion`) | 1969 | 1612 | **81.9 %** |
| `sapphire` (Redmi Note 13 4G, `lineage-24.0`) | 1783 | 1303 | 73.1 % |

creek is the better base (same `mivendor_sm6225` vendor, same HyperOS 3 generation).
sapphire's AMOLED/udfps/NFC borrowings are **not** needed for the parts that matter:
zephyr's own dtbo already contains the p19a panel and the `xiaomi,xiaomi-fp` node, and
its NFC is THN31 rather than sapphire's NXP part.

Zephyr-only files: 2655 of 3980 in `vendor`/`odm`/`*_dlkm` (mostly `vendor/lib*`,
`vendor/bin`, camera tuning, `vendor_dlkm/lib/modules`). Of these, the device-critical
additions over creek are: the four `p19A_*` camera modules, `thn31` NFC stack,
`goodix` FOD firmware/libs, `oca72xxx`/`fs1815` audio amp configs, the p19a panel
`qdcm`/`_mi.xml` files, and the four SKU prop/permission sets.

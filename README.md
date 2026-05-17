<div align="center">
  <img src="https://raw.githubusercontent.com/dortania/OpenCore-Legacy-Patcher/main/docs/images/OC-Patcher.png" alt="OpenCore Legacy Patcher Logo" width="180" />

  # OpenCore Legacy Patcher — T2 Mac Edition

  **Supports Macs with Apple T2 Security Chip · macOS Tahoe / Sequoia**
  
  **รองรับ Mac ที่มีชิป Apple T2 · macOS Tahoe / Sequoia**

  [![Latest Release](https://img.shields.io/github/v/release/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs?label=Latest%20Release&color=blue)](https://github.com/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs/releases/latest)
  [![Build Status](https://img.shields.io/github/actions/workflow/status/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs/build-app-wxpython.yml?label=Build)](https://github.com/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs/actions)
  [![License](https://img.shields.io/github/license/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs)](LICENSE.txt)
  [![Platform](https://img.shields.io/badge/Platform-macOS%20Tahoe%20%7C%20Sequoia-purple)](https://github.com/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs)

</div>

---

## Overview / ภาพรวม

**[EN]** This is a community-maintained fork of [OpenCore Legacy Patcher](https://github.com/dortania/OpenCore-Legacy-Patcher) focused exclusively on **Apple T2 Security Chip Macs**. It resolves boot failures, kernel panics, and display issues specific to T2 hardware running macOS Tahoe (macOS 26) and Sequoia.

**[TH]** นี่คือ fork ที่ดูแลโดยชุมชน จาก [OpenCore Legacy Patcher](https://github.com/dortania/OpenCore-Legacy-Patcher) โดยเน้นเฉพาะ **Mac ที่มีชิป Apple T2** แก้ไขปัญหาการบูต, Kernel Panic และปัญหาหน้าจอที่เกิดขึ้นเฉพาะกับ T2 Mac เมื่อรัน macOS Tahoe (macOS 26) และ Sequoia

> **Based on / อ้างอิงจาก:** albert-mueller/OpenCore-Legacy-Patcher-T2 · Dortania/OpenCore-Legacy-Patcher

---

## Supported Models / รุ่นที่รองรับ

### MacBook Pro

| Model | Marketing Name / ชื่อรุ่น | GPU |
|---|---|---|
| MacBookPro15,1 | MacBook Pro 15-inch 2018 | Intel UHD 630 + AMD Radeon Pro |
| MacBookPro15,2 | MacBook Pro 13-inch 2018 (4 TB3) | Intel Iris Plus 655 |
| MacBookPro15,3 | MacBook Pro 15-inch 2019 | Intel UHD 630 + AMD Radeon Pro |
| MacBookPro15,4 | MacBook Pro 13-inch 2019 (2 TB3) | Intel Iris Plus 655 |
| MacBookPro16,1 | MacBook Pro 16-inch 2019 | Intel UHD 630 + AMD Radeon Pro |
| MacBookPro16,2 | MacBook Pro 13-inch 2020 (4 TB3) | Intel UHD 617 |
| MacBookPro16,3 | MacBook Pro 13-inch 2020 (2 TB3) | Intel UHD 617 |
| MacBookPro16,4 | MacBook Pro 16-inch 2019 CTO | Intel UHD 630 + AMD Radeon Pro |

### MacBook Air

| Model | Marketing Name / ชื่อรุ่น | GPU |
|---|---|---|
| MacBookAir8,1 | MacBook Air 2018 | Intel UHD 617 ✨ |
| MacBookAir8,2 | MacBook Air 2019 | Intel UHD 617 ✨ |
| MacBookAir9,1 | MacBook Air 2020 (Intel) | Intel UHD 617 ✨ |

### Other T2 Macs / T2 Mac รุ่นอื่นๆ

| Model | Marketing Name / ชื่อรุ่น |
|---|---|
| Macmini8,1 | Mac mini 2018 |
| MacPro7,1 | Mac Pro 2019 |
| iMac19,1 | iMac 27-inch 2019 |
| iMac19,2 | iMac 21.5-inch 2019 |
| iMac20,1 | iMac 27-inch 2020 |
| iMac20,2 | iMac 27-inch 2020 CTO |

> ✨ = รองรับเต็มรูปแบบใหม่ใน v1.0.7.1 / Newly added full support in v1.0.7.1

---

## What's Fixed / สิ่งที่แก้ไข

### 🔴 Critical Boot Fixes / แก้ไขปัญหาการบูตหลัก

**`com.apple.kec.corecrypto` Kernel Panic (macOS Tahoe)**

**[EN]**
- Removed `-liluforce` / `-lilubetaall` from T2 Mac boot-args — Lilu injection into `corecrypto` breaks the FIPS POST self-test causing a panic at `_corecrypto_kext_start`
- Added kernel patch to bypass FIPS POST check in `com.apple.kec.corecrypto` (MinKernel 25.0.0)
- T2 Macs now use AMFIPass + `-amfipassbeta` exclusively instead of `amfi=0x80`

**[TH]**
- ลบ `-liluforce` / `-lilubetaall` ออกจาก boot-args ของ T2 Mac — การที่ Lilu inject เข้า `corecrypto` ทำให้ FIPS POST self-test ล้มเหลว เกิด panic ที่ `_corecrypto_kext_start`
- เพิ่ม kernel patch เพื่อข้าม FIPS POST check ใน `com.apple.kec.corecrypto`
- T2 Mac ใช้ AMFIPass + `-amfipassbeta` แทน `amfi=0x80` ทั้งหมด

**Booter & Security Settings**

**[EN]** `SecureBootModel` forced to `Disabled`, `ApECID = 0`, `DmgLoading = Any`, and `UpdateSMBIOSMode = Custom` applied for all T2 Macs.

**[TH]** บังคับ `SecureBootModel = Disabled`, `ApECID = 0`, `DmgLoading = Any` และ `UpdateSMBIOSMode = Custom` สำหรับ T2 Mac ทุกรุ่น

---

### 🟡 Graphics Fixes / แก้ไขปัญหากราฟิก

**Intel UHD 617 — MacBook Air 2018/2019 (ใหม่ใน v1.0.7.1)**

**[EN]**
- Correct connector-less `ig-platform-id 0x3EA50009` (Amber Lake GT3e) now injected
- Previously these models received wrong UHD 630 IDs (`0x3E9B0006`) causing grey screen at boot
- Added `igfxgl=1` + `igfxmetal=1` boot-args to fix grey screen on Tahoe
- `igfxnoredir=1` now scoped to UHD 630 models only

**[TH]**
- ฉีด `ig-platform-id 0x3EA50009` ที่ถูกต้องสำหรับ Amber Lake GT3e
- ก่อนหน้านี้รุ่นเหล่านี้ได้รับ UHD 630 IDs ผิด (`0x3E9B0006`) ทำให้หน้าจอเป็นสีเทาตอนบูต
- เพิ่ม `igfxgl=1` + `igfxmetal=1` เพื่อแก้ grey screen บน Tahoe
- `igfxnoredir=1` ใช้เฉพาะ UHD 630 เท่านั้น

**Intel UHD 630 — MacBook Pro 15/16-inch**

**[EN]** Connector-less `ig-platform-id 0x3E9B0006` to prevent APFS race condition. `igfxonln=1` forces iGPU online. `igfxnoredir=1` fixes white/frozen screen on MacBookPro15,1.

**[TH]** ใช้ `ig-platform-id 0x3E9B0006` แบบ connector-less เพื่อป้องกัน APFS race condition. `igfxonln=1` บังคับให้ iGPU ทำงาน. `igfxnoredir=1` แก้หน้าจอขาว/ค้างบน MacBookPro15,1

---

### 🟢 Stability Fixes / แก้ไขความเสถียร

| Fix / การแก้ไข | EN | TH |
|---|---|---|
| AppleSEPManager patch | Converts SEP timeout panic to return | แปลง SEP panic เป็น return ป้องกันรีบูตกะทันหัน |
| USB handshake bypass | Bypasses T2 USB handshake to prevent boot stall | ข้าม T2 USB handshake ป้องกันเครื่องค้างตอนบูต |
| USB timeout increase | `AppleUSBXHCI` timeout `0x0A → 0xFF` | เพิ่ม timeout USB ให้เมาส์/คีย์บอร์ดตอบสนองทันที |
| InternalHubPowerCheck bypass | Prevents USB hub power state hang | ป้องกัน USB hub ค้างรอสถานะไฟ |
| TouchBar driver patch | Fixes Touch Bar stall on Tahoe | แก้ Touch Bar ค้างบน Tahoe |
| NVMe fix | `nvme_shutdown_timestamp=0` resolves APFS mount stall | แก้ APFS mount ค้าง |
| ipc_control_port_options | Critical T2 communication stall fix | แก้ T2 communication stall |
| corecrypto FIPS bypass | Allows boot via OpenCore unsigned path | อนุญาตให้บูตผ่าน OpenCore |

---

## Installation / การติดตั้ง

### วิธีที่ 1 — ติดตั้งผ่าน PKG (แนะนำ / Recommended)

**[TH]**
1. ดาวน์โหลด `OpenCore-Patcher.pkg` จาก [releases ล่าสุด](https://github.com/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs/releases/latest)
2. รันไฟล์ installer
3. เปิด **OpenCore Legacy Patcher** จาก Applications
4. กด **Build and Install OpenCore**
5. เลือก drive ที่ต้องการและติดตั้ง

**[EN]**
1. Download `OpenCore-Patcher.pkg` from the [latest release](https://github.com/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs/releases/latest)
2. Run the installer
3. Open **OpenCore Legacy Patcher** from Applications
4. Click **Build and Install OpenCore**
5. Select your target drive and install

---

### วิธีที่ 2 — รันจาก Source Code

```bash
# ต้องการ / Requirements: Python 3.10+, Git
git clone https://github.com/GUTY345/OpenCore-Legacy-patcher-t2chip-fixBugs.git
cd OpenCore-Legacy-patcher-t2chip-fixBugs
pip3 install -r requirements.txt

# เปิด GUI / Launch GUI
python3 OpenCore-Patcher-GUI.command
```

---

## Post-Installation / หลังการติดตั้ง

**[TH]** หลังติดตั้ง OpenCore และบูตเข้า macOS Tahoe แล้ว ให้รัน **Post-Install Root Patch** จากแอปเพื่อติดตั้ง GPU drivers และ system patches

ถ้าพบปัญหา ให้รันคำสั่งเหล่านี้ใน Recovery Mode Terminal:

**[EN]** After installing OpenCore and booting into macOS Tahoe, run **Post-Install Root Patch** from the app to install GPU drivers and system patches.

If you encounter issues, run these commands in Recovery Mode Terminal:

```bash
csrutil disable
csrutil authenticated-root disable
```

---

## Boot Arguments / Boot Arguments ที่ใช้ (T2 Macs)

| Argument | Purpose (EN) | วัตถุประสงค์ (TH) |
|---|---|---|
| `-amfipassbeta` | Enable AMFIPass compatibility | เปิดใช้ AMFIPass |
| `-ibtcompatbeta` | Bluetooth compatibility | ความเข้ากันได้ของ Bluetooth |
| `ipc_control_port_options=0` | T2 communication stall fix | แก้ T2 communication ค้าง |
| `igfxonln=1` | Force iGPU online | บังคับ iGPU ให้ทำงาน |
| `igfxfw=2` | Force Apple Graphics Firmware | บังคับ Apple Graphics Firmware |
| `agdpmod=vit9696` | Disable board ID checks | ปิดการตรวจสอบ Board ID |
| `nvme_shutdown_timestamp=0` | APFS mount fix | แก้ APFS mount ค้าง |
| `cryptex=0` | Tahoe cryptex bypass | ข้าม cryptex บน Tahoe |
| `cs_allow_invalid=1` | Allow unsigned code (Tahoe) | อนุญาต unsigned code |
| `forceRenderStandby=0` | Prevent GPU power saving hang | ป้องกัน GPU ค้างจากโหมดประหยัดพลังงาน |
| `igfxgl=1` | Force OpenGL (UHD 617 only) | บังคับ OpenGL สำหรับ UHD 617 |
| `igfxmetal=1` | Enable Metal connector-less (UHD 617) | เปิด Metal บน connector-less |
| `usbmuxd=0x3` | USB multiplexer fix | แก้ USB multiplexer |
| `keepsyms=1` | Preserve kernel symbols | เก็บ kernel symbols ไว้ debug |

---

## Kernel Patches / Kernel Patches ที่ใช้ (T2 Macs, Tahoe)

| Patch | Target | Purpose (EN) | วัตถุประสงค์ (TH) |
|---|---|---|---|
| Bypass corecrypto FIPS POST | `com.apple.kec.corecrypto` | Allow boot via OpenCore | อนุญาตบูตผ่าน OpenCore |
| Bypass T2 USB handshake | `AppleUSBXHCI` | Prevent USB freeze | ป้องกัน USB ค้างตอนบูต |
| Increase USB timeout | `AppleUSBXHCI` | 10ms → 255ms HID response | เพิ่ม timeout USB |
| Bypass InternalHubPowerCheck | `AppleUSBXHCI` | Prevent hub power hang | ป้องกัน USB hub ค้าง |
| SEP Manager panic → return | `AppleSEPManager` | Prevent SEPOS panic | ป้องกัน SEPOS panic |
| TouchBar driver fix | `AppleTouchBarHIDEventDriver` | Fix Touch Bar stall | แก้ Touch Bar ค้าง |
| Disable Library Validation | `kernel` | Allow unsigned kexts | อนุญาต unsigned kexts |

---

## Disclaimer / ข้อความระวัง

> **[EN]** This is an experimental community fork. Use at your own risk. Always back up your data before patching. This project is not affiliated with Apple Inc.
>
> **[TH]** นี่คือ fork ทดลองจากชุมชน ใช้งานด้วยความเสี่ยงของตัวเอง กรุณาสำรองข้อมูลก่อนดำเนินการทุกครั้ง โปรเจกต์นี้ไม่มีความเกี่ยวข้องกับ Apple Inc.

---

## Credits / ทีมงาน

- **[Dortania](https://github.com/dortania)** — Original OpenCore Legacy Patcher / ผู้สร้าง OCLP ต้นฉบับ
- **[albert-mueller](https://github.com/albert-mueller)** — T2 Mac branch foundation / รากฐาน T2 branch
- **[Acidanthera](https://github.com/acidanthera)** — OpenCore, Lilu, WhateverGreen, AMFIPass
- **Mathachai (GUTY345)** — T2 Tahoe fixes, UHD 617 support, maintenance / แก้ไข Tahoe, รองรับ UHD 617, ดูแลรักษา

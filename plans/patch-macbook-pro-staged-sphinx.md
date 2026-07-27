# แผนแก้ไข: MacBookPro15,1 Tahoe Installer Boot — ค้างที่ Apple Logo

> อัพเดท: 2026-07-26 19:10 — ผลทดสอบ: boot คืบหน้ามาก แต่ค้างที่ Apple logo หลัง sks timeout strike 8

---

## 1. สรุปผลวิเคราะห์ Boot Logs (IMG_6691-6694)

### 1.1 ลำดับเหตุการณ์จริงจาก logs

```
Phase 1 — Storage/USB Init (IMG_6691):
  ✅ Kingston DataTraveler 3.0 → USB ตรวจพบ
  ✅ AppleFileSystemDriver → disk2s2 (Untitled 2) = installer HFS partition
  ✅ Apple T2 Controller → USB CDC Composite Device → NCM Control/Data
  ⚠️ AppleUSBECMData probe fails (normal — Ethernet over T2)
  ✅ AppleUSBNCMControl::allocateResources → INT EP 0x81

Phase 2 — GPU/SEP (IMG_6691-6693):
  ❌ WhateverGreen[0x1000005a5]::probe fails ← CRITICAL — WG ไม่ hook เข้า GPU
  ❌ IOSMBusController error - transaction reuse ← T2 SMBus comms error
  ❌ AppleKeyStore sks timeout strike 1 → 2 → 3
  ⚠️ PMRD: System sleep prevented by kPMSystemRestartBootingInProgress

Phase 3 — Kext Loading + Installer (IMG_6694):
  ✅ Lilu <class Lilu, busy 0> ← Lilu โหลดสำเร็จ
  ✅ com_apple_filesystems_apfs loaded
  ✅ hfs: mounted Install macOS Tahoe on device b(1, 12) ← USB mount สำเร็จ
  ✅ imageboot_setup_new: BaseSystem.dmg
  ✅ validate_chunklist: successfully validated ← installer image ผ่าน
  ❌ AppleKeyStore sks timeout strike 8 ← SEP ยังไม่ตอบ

Phase 4 — ค้าง (หลัง IMG_6694):
  ❌ ค้างที่ Apple logo ตลอด — ไม่ไปถึง installer GUI
```

### 1.2 วินิจฉัย

| จุดที่พบ | ความสำคัญ | วิเคราะห์ |
|---------|----------|----------|
| **WhateverGreen probe fails** | 🔴 สูงมาก | WG โหลดสำเร็จแต่ `::probe()` ล้มเหลว → GPU framebuffer อาจไม่ init ถูกต้อง |
| **sks timeout strike 1-8+** | 🔴 สูง | SEP ไม่ตอบสนอง → `AppleKeyStore` ค้าง → disk keybag ปลดล็อกไม่ได้ |
| **Boot ค้างหลัง BaseSystem.dmg validated** | 🔴 สูง | installer image ผ่าน validation แล้ว แต่ system ค้างเพราะ SEP timeout |

### 1.3 Root Cause Analysis

**สาเหตุหลัก: AppleKeyStore (SEP) Timeout**

`"AppleKeyStore":pid:0:3297: sks timeout strike 1-8+` หมายความว่า:
1. kernel ลองสื่อสารกับ T2 SEP ผ่าน `AppleKeyStore` เพื่อปลดล็อก keybag
2. SEP ไม่ตอบสนอง → timeout ซ้ำแล้วซ้ำเล่า
3. boot-arg `check_lock_assert_deadline` patch (Patch 3) bypass แค่ deadline check แต่ SEP ไม่ตอบสนองเลย → patch ช่วยไม่ได้

**สาเหตุรอง: WhateverGreen probe fails**

WhateverGreen probe fails ที่ address `0x1000005a5` → WG ไม่สามารถ hook เข้า iGPU framebuffer driver ได้

---

## 2. แผนแก้ไข — 5 ขั้นตอนทดลอง

### ทดลองที่ 1 (เร็วสุด — เพิ่ม delay ให้ T2 bridge)
**แก้ไข:** `misc.py:542` — เพิ่ม `bpr_initialdelay=500 bpr_finaldelay=500`
**เหตุผล:** เพิ่ม delay ให้ T2 bridge init ก่อน SEP ถูกเรียก → อาจลด sks timeout
**ขั้นตอน:**
1. แก้ `misc.py:542`
2. Rebuild EFI (`python3 OpenCore-Patcher-GUI.command`)
3. Write to USB
4. Boot ทดสอบ → ถ่าย verbose log

### ทดลองที่ 2 (ลบ WhateverGreen ชั่วคราว)
**แก้ไข:** ปิด WhateverGreen.kext (Enabled=False) ใน build process
**เหตุผล:** WG probe fails → อาจก่อกวน GPU init → ลบออกเพื่อดูว่า boot ไปไกลขึ้นหรือไม่
**ขั้นตอน:** เหมือนทดลองที่ 1

### ทดลองที่ 3 (ลบ Patch 3 — check_lock_assert_deadline)
**แก้ไข:** `misc.py:627` — เปลี่ยน `"Enabled": True` → `"Enabled": False`
**เหตุผล:** ดูว่า `check_lock_assert_deadline` bypass เป็นตัวก่อกวนหรือไม่
**ขั้นตอน:** เหมือนทดลองที่ 1

### ทดลองที่ 4 (Combined — แก้ WG + เพิ่ม delay)
**แก้ไข:** combine ทดลองที่ 1 + ที่ 2 เข้าด้วยกัน
**เหตุผล:** ลบ WG + เพิ่ม delay → ตัดตัวก่อกวนทั้งสอง

### ทดลองที่ 5 (ต้องการข้อมูลเพิ่ม — kernel log)
**ขั้นตอน:** เก็บ kernel log หลัง sks timeout → วิเคราะห์ SEP/bridgeOS attestation chain

---

## 3. ไฟล์ที่ต้องแก้

| ไฟล์ | บรรทัด | สิ่งที่แก้ | ทดลอง |
|------|--------|-----------|-------|
| `opencore_legacy_patcher/efi_builder/misc.py` | 542 | เพิ่ม `bpr_initialdelay=500 bpr_finaldelay=500` | #1 |
| `opencore_legacy_patcher/efi_builder/misc.py` | 500 | ปิด WhateverGreen.kext (Enabled=False) | #2 |
| `opencore_legacy_patcher/efi_builder/misc.py` | 627 | ปิด Patch 3 (Enabled=False) | #3 |

---

## 4. ข้อมูลที่ต้องการจากฮาร์ดแวร์จริง

```bash
# 1. kernel log หลัง sks timeout
log show --last 10m --predicate 'process=="kernel" OR senderImagePath CONTAINS "Cyrus" OR senderImagePath CONTAINS "SEP" OR senderImagePath CONTAINS "KeyStore"'

# 2. kextstat
kextstat | grep -iE "Cyrus|Effaceable|SEPManager|NVMe|apfs|WhateverGreen|Lilu"

# 3. ioreg GPU
ioreg -w0 -l | grep -iE "IGPU|GFX0|AppleIntelFramebuffer|WhateverGreen|display"

# 4. diskutil
diskutil apfs list
```

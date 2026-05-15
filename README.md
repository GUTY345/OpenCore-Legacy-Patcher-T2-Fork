<div align="center">
             <img src="https://raw.githubusercontent.com/dortania/OpenCore-Legacy-Patcher/main/docs/images/OC-Patcher.png" alt="OpenCore Patcher Logo" width="256" />
             <h1>OpenCore Legacy Patcher for T2 Macs</h1>
             <p><b>(Mathachai's Bug Fix & Maintenance Branch)</b></p>
</div>

---

### **[TH] เกี่ยวกับ Repo นี้**
Repo นี้จัดทำขึ้นเพื่อ **รวบรวมการแก้ไขบัค (Bug Fixes)** และปรับปรุงเสถียรภาพเพิ่มเติมจากโปรเจกต์หลัก เพื่อให้การใช้งานบนเครื่อง T2 Mac มีความราบรื่นที่สุด โดยเฉพาะปัญหาที่พบใน macOS รุ่นใหม่อย่าง Sequoia และ Tahoe

**🔗 โปรเจกต์หลัก (Main Project):** สามารถติดตามและดาวน์โหลดเวอร์ชันต้นทางได้ที่: [albert-mueller/OpenCore-Legacy-Patcher-T2](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2.git)

#### **รายการที่แก้ไขเพิ่มเติมใน Repo นี้:**
- [x] **UI/UX Fix:** แก้ไขปัญหาปุ่ม "Continue" เป็นสีเทา (กดไม่ได้) ในหน้า Installer ของ T2 Mac
- [x] **Logic Fix:** ปรับปรุง `security.py` เพื่อแก้ปัญหาความปลอดภัยและอาการค้าง (Stall) ระหว่างบูต
- [x] **Stability:** แก้ไขปัญหา `AttributeError` และ Bug อื่นๆ ที่ทำให้การ Build EFI ไม่สมบูรณ์

---

### **[EN] About This Repo**
This repository is dedicated to **bug fixes and maintenance** for the T2-supported branch of OpenCore Legacy Patcher. It aims to resolve specific issues encountered during the development and installation of newer macOS versions on T2 Macs.

**🔗 Main Project Link:** Please refer to the primary upstream repository for core updates: [albert-mueller/OpenCore-Legacy-Patcher-T2](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2.git)

#### **Key Fixes in this Branch:**
- [x] **Installer UI Fix:** Resolved the "Grayed out Continue button" issue on T2 Macs during setup.
- [x] **Security Logic:** Patched `security.py` to bypass boot hangs and improve ASP (Apple System Policy) compatibility.
- [x] **Build Fixes:** Resolved `AttributeError` and script crashes during the EFI creation process.

---

### **📋 รายการการแก้ไขเชิงลึก (Detailed Change Log)**

#### **1. Graphics & UI Fixes (ระบบกราฟิกและอินเตอร์เฟซ)**
* **Connector-less UHD630 Injection**: บังคับฉีด `ig-platform-id` เป็น `06009B3E` สำหรับ Intel UHD 630 เพื่อป้องกัน APFS race condition บน Tahoe ที่ทำให้ระบบค้าง
* **Force GPU Online**: เพิ่ม Boot-arg `igfxonln=1` ป้องกันปัญหาปุ่มกดในหน้าติดตั้งไม่ตอบสนอง (UI Stall)
* **GPU Power Management**: ตั้งค่า `forceRenderStandby=0` ปิดโหมดประหยัดพลังงาน GPU ระหว่างบูต
* **Graphics Firmware**: บังคับใช้ Apple Graphics Firmware ด้วย `igfxfw=2` เพื่อเสถียรภาพสูงสุด

#### **2. Kernel & Stability Patches (ความเสถียรของ Kernel)**
* **SEP Manager Patch**: เปลี่ยน `panic` เป็น `return` ใน `AppleSEPManager` เพื่อแก้ปัญหาเครื่องรีสตาร์ทเอง
* **IOBCC Block**: บล็อกไดรเวอร์ `IOBufferCopyController` ป้องกัน Kernel Panic "timed out" บน macOS Tahoe
* **T2 Boot Overrides**: บังคับตั้งค่า `SecureBootModel = Disabled` และ `ApECID = 0` เพื่อการันตีการบูต

#### **3. Storage & I/O Fixes (ระบบจัดเก็บข้อมูลและอุปกรณ์เชื่อมต่อ)**
* **NVMe Mount Fix**: เพิ่ม `nvme_shutdown_timestamp=0` แก้ปัญหาการเมานท์พาร์ทิชัน APFS ค้าง (Stall)
* **USB Timeout Extension**: ขยายเวลา `AppleIntelUSBXHC` Timeout เป็น 255ms (0xFF) ให้เมาส์/คีย์บอร์ดใช้งานได้ทันที
* **USB Handshake Bypass**: แพตช์ข้ามขั้นตอน T2 USB handshake ป้องกันอุปกรณ์ค้างระหว่างเริ่มต้นระบบ
* **APFS Stability**: ปิดการตรวจสอบ GPU ของ APFS และเปิด `keepsyms=1` เพื่อให้การ Replay Journal ทำงานสมบูรณ์

---

### **💻 รุ่นที่รองรับ (Supported Models)**
* **MacBook Pro**: 15,1 / 15,3 / 16,1 / 16,4
* **Mac mini**: 8,1
* **MacBook Air**: 8,1 / 8,2 / 9,1
* **Mac Pro**: 7,1

---

## ⚠️ Disclaimer
โปรเจกต์นี้เป็นการนำซอร์สโค้ดมาปรับปรุงเพื่อแก้ปัญหาเฉพาะหน้า (Experimental Bug Fixes) การใช้งานมีความเสี่ยง กรุณาสำรองข้อมูลสำคัญก่อนดำเนินการทุกครั้ง

**หมายเหตุสำคัญ:** เพื่อให้แพตช์ทำงานสมบูรณ์บน Tahoe ต้องรันคำสั่ง `csrutil authenticated-root disable` ใน Recovery Mode

## Credits
ขอขอบคุณผู้พัฒนาหลักและทีมงาน OCLP ทุกท่าน:
* **Albert Müller** - ผู้พัฒนาหลักของ [T2-specific branch](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2)
* **Dortania & Acidanthera** - ทีมพัฒนา OpenCore และ OCLP ต้นฉบับ
* และเหล่านักพัฒนาในชุมชน Open Source ทุกคนที่ร่วมกันทำให้เครื่อง Mac รุ่นเก่าไปต่อได้
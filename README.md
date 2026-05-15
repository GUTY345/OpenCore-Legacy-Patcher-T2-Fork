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

## ⚠️ Disclaimer
โปรเจกต์นี้เป็นการนำซอร์สโค้ดมาปรับปรุงเพื่อแก้ปัญหาเฉพาะหน้า (Experimental Bug Fixes) การใช้งานมีความเสี่ยง กรุณาสำรองข้อมูลสำคัญก่อนดำเนินการทุกครั้ง

## Credits
ขอขอบคุณผู้พัฒนาหลักและทีมงาน OCLP ทุกท่าน:
* **Albert Müller** - ผู้พัฒนาหลักของ [T2-specific branch](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2)
* **Dortania & Acidanthera** - ทีมพัฒนา OpenCore และ OCLP ต้นฉบับ
* และเหล่านักพัฒนาในชุมชน Open Source ทุกคนที่ร่วมกันทำให้เครื่อง Mac รุ่นเก่าไปต่อได้

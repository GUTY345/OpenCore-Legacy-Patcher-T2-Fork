<div align="center">
  <img src="https://raw.githubusercontent.com/dortania/OpenCore-Legacy-Patcher/main/docs/images/OC-Patcher.png" alt="OpenCore Patcher Logo" width="200" />
  <h1>🚀 OpenCore Legacy Patcher (T2 Branch)</h1>
  <p><b>Custom Maintenance & Bug Fixes for macOS Tahoe/Sequoia on T2 Macs</b></p>
  <p><i>สาขาสำหรับการบำรุงรักษาและแก้ไขบัคสำหรับเครื่อง T2 โดยเฉพาะ</i></p>

  [![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/GUTY345/OpenCore-Legacy-Patcher-T2-main)
  [![Platform](https://img.shields.io/badge/Platform-macOS%20Tahoe%20%7C%20Sequoia-blue.svg)](https://github.com/GUTY345/OpenCore-Legacy-Patcher-T2-main)
</div>

---

## 📖 Table of Contents / สารบัญ
1. About / เกี่ยวกับโปรเจกต์
2. Key Fixes / รายการการแก้ไข
3. Supported Models / รุ่นที่รองรับ
4. Getting Started / วิธีการใช้งาน
5. Post-Installation / คำสั่งหลังติดตั้ง

---

## ℹ️ About / เกี่ยวกับโปรเจกต์

**[TH]** Repo นี้จัดทำขึ้นเพื่อรวบรวมการแก้ไขบัค (Bug Fixes) และปรับปรุงเสถียรภาพเพิ่มเติมจากโปรเจกต์หลัก เพื่อให้เครื่อง **T2 Mac** ใช้งาน macOS Sequoia และ Tahoe ได้ราบรื่นที่สุด

**[EN]** This repository focuses on maintenance and stability improvements for **T2 Macs**. It resolves specific issues found when running macOS Sequoia and Tahoe via OpenCore.

> **Main Project:** albert-mueller/OpenCore-Legacy-Patcher-T2

---

## 🛠️ Key Fixes (Detailed Change Log) / รายการการแก้ไขเชิงลึก

### 📺 Graphics & UI / กราฟิกและอินเตอร์เฟซ
| Feature | Detail (EN) | รายละเอียด (TH) |
| :--- | :--- | :--- |
| **UHD630 Injection** | Forced `06009B3E` to prevent APFS race condition. | บังคับฉีด ID ป้องกันเครื่องค้างจาก APFS |
| **GPU Online** | Added `igfxonln=1` to fix unresponsive buttons. | แก้ไขปุ่ม Continue กดไม่ได้ในหน้าติดตั้ง |
| **GPU Power** | `forceRenderStandby=0` to prevent boot hangs. | ปิดโหมดประหยัดพลังงาน GPU ระหว่างบูต |

### 🧠 Kernel & Stability / ความเสถียรของระบบ
| Feature | Detail (EN) | รายละเอียด (TH) |
| :--- | :--- | :--- |
| **SEP Manager** | Patched panic to return to prevent reboots. | แก้ไข Kernel Panic จากระบบความปลอดภัย SEP |
| **IOBCC Block** | Blocked `IOBufferCopyController` timeout fix. | บล็อกไดรเวอร์ที่ทำให้ Tahoe เกิดอาการ Timeout |
| **USB Timeout** | Increased to `0xFF` for instant HID response. | ขยายเวลา USB ให้เมาส์/คีย์บอร์ดตอบสนองไวขึ้น |

### 💾 Storage & I/O / ข้อมูลและการเชื่อมต่อ
| Feature | Detail (EN) | รายละเอียด (TH) |
| :--- | :--- | :--- |
| **NVMe Fix** | `nvme_shutdown_timestamp=0` for APFS mount. | แก้ปัญหาการเมานท์พาร์ทิชัน APFS ค้าง |
| **USB Handshake** | Bypassed T2 handshake to prevent boot stall. | ข้ามขั้นตอนเช็ค USB เพื่อไม่ให้เครื่องค้างตอนเริ่ม |

---

## 💻 Supported Models / รุ่นที่รองรับ
*   **MacBook Pro:** 15,1 / 15,3 / 16,1 / 16,4
*   **Mac mini:** 8,1
*   **MacBook Air:** 8,1 / 8,2 / 9,1
*   **Mac Pro:** 7,1

---

## 🚀 Getting Started / วิธีการใช้งานเบื้องต้น

### 1️⃣ Prerequisites / การเตรียมระบบ
*   **Python 3.10+**
*   **Git** & **Xcode Command Line Tools**

### 2️⃣ Installation / การติดตั้ง
```bash
# Clone and setup / ดาวน์โหลดและติดตั้ง
git clone https://github.com/GUTY345/OpenCore-Legacy-Patcher-T2-main.git
cd OpenCore-Legacy-Patcher-T2-main
pip3 install -r requirements.txt
```

### 3️⃣ Running / การเริ่มโปรแกรม
*   **GUI Mode:** `python3 OpenCore-Patcher-GUI.command`
*   **CLI Mode:** `python3 OpenCore-Patcher.py`

---

## 🛠️ Post-Installation Commands / คำสั่งที่ต้องรันหลังติดตั้ง

> [!IMPORTANT]
> **[TH]** เพื่อให้ Patch ทำงานสมบูรณ์บน Tahoe ต้องรันคำสั่งเหล่านี้ใน Recovery Mode (Terminal)
> **[EN]** For full functionality on Tahoe, run these in Recovery Mode Terminal:

```bash
csrutil disable
csrutil authenticated-root disable
```

---

## ⚠️ Disclaimer / ข้อความระวัง

**[TH]** โปรเจกต์นี้เป็นการแก้ไขเพื่อทดสอบ (Experimental) การใช้งานมีความเสี่ยง กรุณาสำรองข้อมูลก่อนดำเนินการ
**[EN]** This is an experimental branch. Use at your own risk. Always back up your data before patching.

---

## 🤝 Credits / ทีมงาน
*   **Albert Müller** - T2-specific branch lead.
*   **Dortania & Acidanthera** - Original OCLP developers.
*   **Mathachai** - Maintenance & Tahoe specific fixes.

<div align="center">
             <img src="docs/images/OC-Patcher.png" alt="OpenCore Patcher Logo" width="256" />
             <h1>OpenCore Legacy Patcher for T2 Macs Alpha</h1>
</div>

A Python-based project revolving around [Acidanthera's OpenCorePkg](https://github.com/acidanthera/OpenCorePkg) and [Lilu](https://github.com/acidanthera/Lilu) for both running and unlocking features in macOS on supported and unsupported Macs, with security in mind.

> **⚠️ EXPERIMENTAL FORK** — Adds **macOS 15 Sequoia and macOS 26 Tahoe support for T2 Macs**. T2 Macs as of now are unsupported by the official OpenCore Legacy Patcher from Dortania. Use it at your own risk. It's still in alpha stage, so I highly recommend to backup all your data and do it only on a spare T2 Mac to experiment.
## T2 Mac Support

> **⚠️ Attention, please!** If you download OpenCore Legacy Patcher T2 from Code > Download, you may run into bugs because I'm writing the code mostly directly from GitHub's interface. If you want to avoid running into weird bugs, I recommend to download from Releases instead.

> **⚠️Warnung!** Wenn Sie OpenCore Legacy Patcher T2 über Code > Download herunterladen, in der App kann einige Bugs auftreten, weil ich den Code größtenteils direkt über GitHubs Oberfläche schreibe. Um diese zu vermeiden, es ist empfohlen den OpenCore Legacy Patcher T2-App stattdessen über Releases herunterzuladen.

> **🚧 Not ready for general use**

> **Progress:**
- [x] Upgrade config.plist to OpenCore 1.0.7 - done
- [X] Upgrade WhateverGreen and Lilu to the latest version - done
- [X] Upgrade OpenCore-RELEASE.zip to OpenCore 1.0.7
- [X] Upgrade OpenCore-DEBUG.zip to OpenCore 1.0.7
- [X] Fix https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/23 - done
- [X] Update RestrictEvents to 1.1.6 - done
- [X] Update CryptexFixup to 1.0. - done
- [X] Update FeatureUnlock to 1.1.8 - done
- [X] Set DisableIoMapper to True for T2 Macs - done
- [X] Remove USB port mapping for MacBookAir8,1 and 8,2 - done
- [X] Fix https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/25 
- [X] Return support for MacBookAir8,1 and MacBookAir8,2

Our goal of this project is to add support for T2 Macs so unsupported T2 Macs can boot into Sequoia and Tahoe. This project may run on non-T2 Macs, but support is limited for those and that's not the focus of this project.



----------

![GitHub all releases](https://img.shields.io/github/downloads/dortania/OpenCore-Legacy-Patcher/total?color=white&style=plastic) ![GitHub top language](https://img.shields.io/github/languages/top/dortania/OpenCore-Legacy-Patcher?color=4B8BBE&style=plastic) ![Discord](https://img.shields.io/discord/417165963327176704?color=7289da&label=discord&style=plastic)

----------

Noteworthy features of OpenCore Legacy Patcher:

* Support for macOS Big Sur, Monterey, Ventura, Sonoma, Sequoia and eventually add support for Tahoe.
* Native Over the Air (OTA) System Updates
* Supports Penryn and newer Macs
* Full support for WPA Wi-Fi and Personal Hotspot on BCM943224 and newer wireless chipsets
* System Integrity Protection, FileVault 2, .im4m Secure Boot and Vaulting
* Recovery OS, Safe Mode and Single-user Mode booting on non-native OSes
* Unlocks features such as Sidecar and AirPlay to Mac even on native Macs
* Enables enhanced SATA and NVMe power management on non-Apple storage devices
* Zero firmware patching required (ie. APFS ROM patching)
* Graphics acceleration for both Metal and non-Metal GPUs

----------

Note: Only clean-installs and upgrades are supported. macOS Big Sur installs already patched with other patchers, such as [Patched Sur](https://github.com/BenSova/Patched-Sur) or [bigmac](https://github.com/StarPlayrX/bigmac), cannot be used due to broken file integrity with APFS snapshots and SIP. Here's an exception: if you are already using patchers like OCLP-Mod or the official OpenCore Legacy Patcher by Dortania, you can revert the root patches and upgrade to this patcher. But that's not the case with OCLP-Plus, since OCLP-Plus leaves the integrity with APFS snapshots and SIP broken.

* You can, however, reinstall macOS with this patcher and retain your original data

Note 2: Currently, OpenCore Legacy Patcher officially supports patching to run macOS Big Sur through Sonoma installs. For older OSes, OpenCore may function; however, support is currently not provided from Dortania.

* For macOS Mojave and Catalina support, we recommend the use of [dosdude1's patchers](http://dosdude1.com)

## Getting Started

To start using the project, please see our in-depth guide:

* [OpenCore Legacy Patcher Guide](https://dortania.github.io/OpenCore-Legacy-Patcher/)

## Support

This project is offered on an AS-IS basis, we do not guarantee support for any issues that may arise. However, there is a community server with other passionate users and developers that can aid you:

* [OpenCore Patcher Paradise Discord Server](https://discord.gg/rqdPgH8xSN)
  * Keep in mind that the Discord server is maintained by the community, so we ask everyone to be respectful.
  * Please review our docs on [how to debug with OpenCore](https://dortania.github.io/OpenCore-Legacy-Patcher/DEBUG.html) to gather important information to help others with troubleshooting.

## Running from source

To run the project from source, see here: [Build and run from source](./SOURCE.md)

## Credits

* [Acidanthera](https://github.com/Acidanthera)
  * OpenCorePkg, as well as many of the core kexts and tools
* [DhinakG](https://github.com/DhinakG)
  * Main co-author
* [Khronokernel](https://github.com/Khronokernel)
  * Main co-author
  * Great amounts of help with debugging, and code suggestions
* [Ausdauersportler](https://github.com/Ausdauersportler)
  * iMacs Metal GPUs Upgrade Patch set and documentation
* [vit9696](https://github.com/vit9696)
* [Albert Müller](https://github.com/albert-mueller/)
  * Adding support for unsupported T2 Macs and the main author of this fork
  * Help troubleshooting, determining fixes and writing patches
* [vytska69](https://github.com/vytska69)
  * [developing patches for the T2 chip](https://github.com/vytska69/OpenCore-Legacy-Patcher)
  * [Developing Secure Enclave Processor (SEP) timeout patches](https://github.com/vytska69/OpenCore-Legacy-Patcher)
  * [workflow files](https://github.com/vytska69/OpenCore-Legacy-Patcher)
* [kodeaqua](https://github.com/kodeaqua)
  * for research on MacBook Air 2018-2019 hardware to fix boot issues
* [GUTY345](https://github.com/GUTY345)
  * for fixing a bug in OpenCore Legacy Patcher T2 where USB-Map.plist's syntax was invalid and SMBIOS spoofing bug that prevented SMBIOS spoofing from working properly on T2 Macs
* [EduCovas](https://github.com/covasedu)
  * [non-Metal patch set](https://github.com/moraea/non-metal-frameworks) for nVidia Tesla/Fermi/Maxwell/Pascal, AMD TeraScale 1/2, and Intel Core 1st/2nd Generation GPUs
  * [3802 Metal patch set](https://github.com/moraea/misc-patches/tree/main/3802-Metal-15) and [MetallibSupportPkg](https://github.com/dortania/MetallibSupportPkg) for nVidia Kepler and Intel Core 3rd/4th Generation GPUs
  * Metal bundle patches and shims for [nVidia Kepler](https://github.com/moraea/misc-patches/tree/main/Kepler%2013%2B), [AMD GCN 1 - 4](https://github.com/moraea/misc-patches/tree/main/GCN%2013%2B), and [AMD GCN 5 (Vega)](https://github.com/moraea/misc-patches/tree/main/vega%2013%2B)
  * [IOSurface offset patches](https://github.com/moraea/misc-patches/tree/main/Sonoma%2014.4%20IOSurface) for nVidia Kepler, AMD GCN 1 - 5, and Intel Core 3rd - 6th Generation GPUs
  * [legacy Wi-Fi patch set](https://github.com/moraea/unsupported-wifi-patches) restores functionality for Wi-Fi cards in all 2007 - 2017 models
  * [T1 patch set](https://github.com/moraea/misc-patches/tree/main/T1-Patch) restores Touch ID, Apple Pay, and other secure functionality in 2016 - 2017 models
  * AppleGVA downgrade for accelerated video decoding on 2012 - 2016 models
  * OpenCL and OpenGL downgrade for AMD GCN
  * [USB 1 patch](https://github.com/moraea/misc-patches/tree/main/IOUSBHostFamily-14.4)

* [ASentientHedgehog](https://github.com/moosethegoose2213)
  * [non-Metal patch set](https://github.com/moraea/non-metal-frameworks) for nVidia Tesla/Fermi/Maxwell/Pascal, AMD TeraScale 1/2, and Intel Core 1st/2nd Generation GPUs

* [ASentientBot](https://github.com/ASentientBot)
  * [non-Metal patch set](https://github.com/moraea/non-metal-frameworks) for nVidia Tesla/Fermi/Maxwell/Pascal, AMD TeraScale 1/2, and Intel Core 1st/2nd Generation GPUs
  * [Metal bundle interposer](https://github.com/moraea/misc-patches/tree/main/sequoia%2031001%20interposer) for AMD GCN 1 - 5 and Intel Core 5th/6th Generation GPUs
  * [dsce](https://github.com/moraea/dsce) and [shared code](https://github.com/moraea/moraea-common) used by some other patches
* [cdf](https://github.com/cdf)
  * Mac Pro on OpenCore Patch set and documentation
  * [Innie](https://github.com/cdf/Innie) and [NightShiftEnabler](https://github.com/cdf/NightShiftEnabler)
* [Syncretic](https://forums.macrumors.com/members/syncretic.1173816/)
  * [AAAMouSSE](https://forums.macrumors.com/threads/mp3-1-others-sse-4-2-emulation-to-enable-amd-metal-driver.2206682/), [telemetrap](https://forums.macrumors.com/threads/mp3-1-others-sse-4-2-emulation-to-enable-amd-metal-driver.2206682/post-28447707) and [SurPlus](https://github.com/reenigneorcim/SurPlus)
* [dosdude1](https://github.com/dosdude1)
  * Main author of the [original GUI](https://github.com/dortania/OCLP-GUI)
  * Development of previous patchers, laying out much of what needs to be patched
* [parrotgeek1](https://github.com/parrotgeek1)
  * [VMM Patch Set](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/4a8f61a01da72b38a4b2250386cc4b497a31a839/payloads/Config/config.plist#L1222-L1281)
* [BarryKN](https://github.com/BarryKN)
  * Development of previous patchers, laying out much of what needs to be patched
* [mario_bros_tech](https://github.com/mariobrostech) and the rest of the Unsupported Mac Discord
  * Catalyst that started OpenCore Legacy Patcher
* [arter97](https://github.com/arter97/)
  * [SimpleMSR](https://github.com/arter97/SimpleMSR/) to disable firmware throttling in Nehalem+ MacBooks without batteries
* [Mr.Macintosh](https://mrmacintosh.com)
  * Endless hours helping architect and troubleshoot many portions of the project
* [flagers](https://github.com/flagersgit)
  * Aid with Nvidia Web Driver research and development
  * [non-Metal patch set](https://github.com/moraea/non-metal-frameworks) for nVidia Tesla/Fermi/Maxwell/Pascal, AMD TeraScale 1/2, and Intel Core 1st/2nd Generation GPUs
  * [Metal bundle interposer](https://github.com/moraea/misc-patches/tree/main/sequoia%2031001%20interposer) for AMD GCN 1 - 5 and Intel Core 5th/6th Generation GPUs
  * LegacyRVPL, SnapshotIsKill, etc. to aid in rapid testing and development
* [joevt](https://github.com/joevt)
  * [FixPCIeLinkrate](https://github.com/joevt/joevtApps)
* [Jazzzny](https://github.com/Jazzzny)
  * Research and various contributions to the project
  * UEFI Legacy XHCI research and development
  * NVIDIA OpenCL research and development
  * `MacBook5,2` research and development
    * LegacyKeyboardInjector
  * Pre-Ivy Bridge Aquantia Ethernet Patch
  * Non-Metal Photo Booth Patch for Monterey+
  * GUI and Backend Development
    * Updater UI
    * macOS Downloader UI
    * Downloader UI
    * USB Top Case probing
    * Developer root patching
  * Vaulting implementation
  * macOS 15 3802 Helios Research
  * UEFI bootx64.efi research
  * universal2 build research
  * Various documentation contributions
* Amazing users who've graciously donate hardware:
  * [JohnD](https://forums.macrumors.com/members/johnd.53633/) - 2013 Mac Pro
  * [SpiGAndromeda](https://github.com/SpiGAndromeda) - AMD Vega 64
  * [turbomacs](https://github.com/turbomacs) - 2014 5k iMac
  * [vinaypundith](https://forums.macrumors.com/members/vinaypundith.1212357/) - MacBook7,1
   * [ThatStella7922](https://github.com/ThatStella7922) - 2017 13" MacBook Pro (A1708)
  * zephar - 2008 Mac Pro
  * jazo97 - 2011 15" MacBook Pro
  * And others (reach out if we forgot you!)
* MacRumors and Unsupported Mac Communities
  * Endless testing and reporting issues
* Apple
  * for macOS and many of the kexts, frameworks and other binaries we reimplemented into newer OSes

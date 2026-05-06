# OpenCore Legacy Patcher T2 changelog
## 3.1.1 pre-alpha release candidate / 3.1.1 Voralpha Releasekandidat 3:
This release:
- Replaces broken ocvalidate and macserial with a functioning one to fix https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/29
- Continues to roll out patches to fix the T2 controller panic AppleUSBXHCI::createPorts: unsupported speed mantissa 5830 exponent 2 panic when pressing ->

Dieses Version:
- Ersetzt das kapputen ocvalidate und macserial mit einen, die funktioniert, um den Fehler https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/29 zu verbessern .
- Weiterfahren, Verbesserungen auszurollen, um das Fehler, indem beim Anklicken der Pfeil -> in Sprache auswählen, der T2-Kontroller mit dem Fehler AppleUSBXHCI::createPorts: unsupported speed mantissa 5830 exponent 2 panic abstürzt

## 3.1.1 pre-alpha release candidate / 3.1.1 Voralpha Releasekandidat 2:
This release:
- fixes a bug where RestrictEvents.kext wasn't injected
- SecureBootModel in the config.plist was set to Default but it was in a weird state because it used the Default model from 1.0.5 instead of the updated one from 1.0.7 
- Starting to roll out fixes for a bug where MacBook Air 2018, MacBook Air 2019 and MacBook Pro 2020 2 USB 3 ports when booting the installer, as soon as the user presses -> to choose a language, the T2 controller kernel panics with the SHC1@14000000: AppleUSBXHCI::createPorts: unsupported speed mantissa 5830 exponent 2 panic
Dieses Version: 
- verbessert einen Fehler, indem RestrictEvents.kext nicht injiziert war
- Das SecureBootModel war auf Default eingestellt, aber war in kommischen Status, weil es verwendete das Modell von OpenCore 1.0.5 stattdessen von OpenCore 1.0.7
- Fängt an, Verbesserungen für einen Fehler, sobald der Installationsprogramme auf der MacBook Air 2018, MacBook Air 2019, MacBook Air 2020 2 USB-3 ports, wenn der Benutzer den Pfeil klickt, der T2-Controller stürzt ab mit dem Fehler SHC1@14000000: AppleUSBXHCI::createPorts: unsupported speed mantissa 5830 exponent 2, auszurollen

## 3.1.1 pre-alpha release candidate / 3.1.1 Voralpha Releasekandidat:
This release:

Fix a vulnerability where updates may not be delivered properly - this vulnerability affects both this repository and Dortania's
Fix an update suppression vulnerability where an attacker may hide from the users that they aren't running the latest version of the patcher - this vulnerability affects both this repository and Dortania's
Fix a vulnerability where when trying to update, instead it visits this repository, ending up in a loop that causes CPU cycles
Another release candidate will be released shortly.

## 3.1.1 pre-alpha 5:
This release:
- upgrades OpenCore-DEBUG.zip to OpenCore 1.0.7
- upgrades OpenCore-RELEASE.zip to OpenCore 1.0.7
- Fixes a bug where when trying to build OpenCore EFI on unsupported T2 Macs it couldn't find the RestrictEvents kext
- Updates macserial to OpenCore 1.0.7
- Updates ocvalidate to OpenCore 1.0.7

The following issues are known:
https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/24
The following issues remain to be tested whether are fixed or not:
https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/18 and https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/8

## 3.1.1 pre-alpha 4:
This release:

Removes USB port mapping for MacBookAir8,1 and 8,2 - this can eventually cause hangs
Fix #23
## 3.1.1 pre-alpha 3:
## Security & Privacy Improvements
Deprecated Third-Party KDK Endpoints: Completely removed dependency on third-party proxies (OMAPIv1 / OMAPIv2) for Kernel Debug Kit retrieval.

Eliminated Telemetry Tracking: Stopped sending client IP addresses, request intervals, and OS build metadata to external non-Dortania endpoints.

Mitigated Supply Chain & MitM Risks: Enforced direct and secure connections to the official Dortania GitHub repository (KDK_API_LINK_ORIGIN) to prevent Man-in-the-Middle (MitM) attacks caused by unencrypted HTTP fallbacks.

Enhanced Local Integrity Validation: Tightened the validation process for existing KDK installations, reducing reliance on legacy insecure verification scripts.

## Why These Changes Matter
For users and developers, transitioning from the third-party implementation back to Dortania’s original infrastructure provides significant improvements:

Data Privacy: Your system's IP address, patcher version, and build configuration are no longer logged by intermediate SimpleHac servers.

Supply Chain Security: Downloads are retrieved solely via Dortania's official release mirrors, ensuring the authenticity of the binaries.
## Other changes include:
- Changed DisableIoMapper from False to True for T2 Macs
- Update RestrictEvents to 1.1.6
- Update CryptexFixup to 1.0.5
- Update FeatureUnlock to 1.1.8 

## Emergency update for alpha users only: 3.1.0 alpha 3.0:
This is an emergency update. 
## Changelog
Security & Privacy Improvements
Deprecated Third-Party KDK Endpoints: Completely removed dependency on third-party proxies (OMAPIv1 / OMAPIv2) for Kernel Debug Kit retrieval.

Eliminated Telemetry Tracking: Stopped sending client IP addresses, request intervals, and OS build metadata to external non-Dortania endpoints.

Mitigated Supply Chain & MitM Risks: Enforced direct and secure connections to the official Dortania GitHub repository (KDK_API_LINK_ORIGIN) to prevent Man-in-the-Middle (MitM) attacks caused by unencrypted HTTP fallbacks.

Enhanced Local Integrity Validation: Tightened the validation process for existing KDK installations, reducing reliance on legacy insecure verification scripts.

## Why These Changes Matter
For users and developers, transitioning from the third-party implementation back to Dortania’s original infrastructure provides significant improvements:

Data Privacy: Your system's IP address, patcher version, and build configuration are no longer logged by intermediate SimpleHac servers.

Supply Chain Security: Downloads are retrieved solely via Dortania's official release mirrors, ensuring the authenticity of the binaries.


## 3.1.1 pre-alpha 3:
This release:
- Removes USB port mapping for MacBookAir8,1 and 8,2 - this can eventually cause hangs
- Fix https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/23

## 3.1.1 pre-alpha 2.1:
This release fixes a config.plist bug that doesn't build OpenCore properly on non-T2 Macs. On T2 Macs, this issue remains: https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/23

## 3.1.1 pre-alpha 2:
- upgrades config.plist to OpenCore 1.0.7
- Upgrades WhateverGreen to 1.7.0
- Upgrades Lilu to 1.72
- Fix a vulnerability that lets attackers skip injecting necessary T2 kexts to launch a DoS attack - this vulnerability affects this repository only)
- Fix a vulnerability that lets attackers claim the EFI is built when the EFI is broken to launch a DoS attack on any Mac - this vulnerability affects this repository only
To fix these vulnerabilities, if you are running 3.1.1 pre-alpha 1, update immediately to the latest pre-alpha release. If you are using the alpha version instead, you should wait until a later alpha version is released since this vulnerability is not patched yet.

## 3.1.1 pre-alpha 1:
This version begins the upgrade from OpenCore 1.0.5 to 1.0.7 (but hasn't fully upgraded yet). Still it uses mostly 1.0.5.

## 3.1.0 alpha 2.1:
This release:
- blacks out Build OpenCore on 2018-2019 MacBook Airs since these models frequently freeze at the Apple logo. This project still uses OpenCore 1.0.5, upgrading to OpenCore 1.0.7 is planned to eventually begin to fix the following issues: https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/18 and https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/8 and eventually, get the MacBookAir8,1 and 8,2 to boot reliably into macOS's installer. Outside this release, in the branch https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/tree/opencore-1-0-7-upgrade I started upgrading to OpenCore 1.0.7, but the code is considered at a pre-alpha stage and is still in very very early development. To test building OpenCore EFI on these models (if you are ready to experiment), you will need to go to the model_array file and remove # from the model that you are going to be testing. 
- phases out iBridged.kext completely- not needed
- removes SSDT-T2-SPOOF.dsl as it only spoofed the iBridged version that the T2 chip is running and this is not needed; replaced with [SSDT-T2-SPOOF-SSDT.txt](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/blob/main/SSDT-T2-SPOOF-SSDT.txt), [T2-Lilu-hooks.txt](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/blob/main/T2-Lilu-hooks.txt) and [T2-costum-kext-concept.txt](https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/blob/main/T2-costum-kext-concept.txt) - they aren't precompiled and ready to use, rather than there to do research.
- Remove temporarily Info-Tahoe.plist from AppleUSBMaps (this doesn't affect the OpenCore 1.0.7 upgrade branch), as this is not a full USB port map and as such is incomplete and not even close to ready for testing (this is included in the official OpenCore Legacy Patcher 3.0.0).

The issues https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/8 and https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/18 aren't fixed yet. Both of these require to upgrade OpenCore to version 1.0.7 at very minimum for sure.

Reminder: before to boot into OpenCore on T2 Macs, don't forget to hold command + R until macOS Recovery loads. Then go to Utilities > Terminal. Then, type the following commands:
csrutil disable
csrutil-authenticated boot disable
And then go to Apple Logo > Restart. Then you can boot into OpenCore and boot into macOS's installer.

## 3.1.0 alpha 2:
This release:
- fixes duplicate NVRAM arguments for T2 Macs, which in some cases can cause T2 Macs to stall at the Apple logo or attackers to abuse this via Buffer Overflow vulnerabilities
- Switching back to Dortania's own PatcherSupportPkg, this time using the latest version that is available
- On MacBook Air 2018 and 2019, if you download the macOS 15 Sequoia via the OpenCore Legacy Patcher T2 app, now it will disable WhateverGreen. However, if you use an existing installer or just build OpenCore using macOS 14 Sonoma, then it will still enable WhateverGreen.
- Fix Function Error: 'NoneType' object does not support item assignment
- Exclude MacBookPro15,4 from the Board ID exemption patches
- Fix a bug where a missing comma prevented Mac mini 2018 and MacBook Pro 2020 2 thunderbolt 3 ports from getting excluded from the Boot Logo patches
- exclude the iMac Pro from Boot Logo patches
- Fix a vulnerability where when patching T1 Macs, attackers can launch State of Confusion attacks, Denial of Service attacks or malformed imputs - this vulnerability affects all versions of this repository until 3.1.0 alpha 1 and also affects the official OpenCore Legacy Patcher by Dortania repo too
## 3.1.0 alpha 1:
This release removes iBridged.kext in favor of SSDT patching that automated patch via the OpenCore Legacy Patcher app is not written yet - so you need after building the EFI to add the file via OCAT. And from this release onwards, PatcherSupportPkg files will be downloaded from OCLP-Mod's fork rather than directly from Dortania as they have better macOS 26 support. If you come across a bug where something doesn't download properly, make sure to report this issue and eventually suggest a fix as this project has just started transitioning from Dortania's PatcherSupportPkg to the one used by OCLP-Mod.

## 3.0.0 alpha 15:
This release adds the following fixes:
- fixes port mapping logic bugs and connector bugs for the USB ports on MacBook6,1 and 6,2
- Partial iBridged patching logic (not fully done yet, so it may not add iBridged into the kexts automatically yet)

Adding the following from https://github.com/vytska69/OpenCore-Legacy-Patcher that are made by vytska69 into this repository:
- Added .github/workflows (imported from the repository above)
- Adding the following patches:
- Add AMFI patches and set boot-args to -v rddelay=5 amfi_get_out_of_my_way=0x1 igfxfw=2 igfxonln=1
-  Add MacBookAir8,1 and MacBookAir8,2 USB patches
- Add AppleSEPManager patches
- Disable Board ID exemption patches
- Disabling Boot Logo patches to prevent kernel panics and boot loops from occuring
- Enable WhateverGreen on unsupported T2 Macs if necessary
- fix: make gktool scan non-fatal in PKG postinstall script

The only thing that remains to be tested is whether T2 Macs can now properly boot into macOS 15 and 26's installers and finish the implementation of the patches for iBridged.kext.
## 3.0.0 alpha 14:
This release adds a stable version of WhateverGreen.kext directly from Dortania. But how good it works with iBridged remains to be tested.

## 3.0.0 alpha 13:
This version removes the broken WhateverGreen.kext from the code. When there is a new fully functional file, I'll add it again.

## 3.0.0 alpha 12:
This release fixes the following issues:
GUI and Backend Improvements
Fix Build & Install Frame Stability:

Implemented finally blocks in gui_build.py and gui_install_oc.py to ensure logging handlers are properly detached.

This resolves the RuntimeError: C/C++ object has been deleted when transitioning between build and installation screens.

Refactor Thread Management:

Replaced index-based handler removal (handlers[2]) with explicit object references.

Fixes IndexError: list index out of range occurring on faster machines or when disk unmounting is delayed.

Improve Installation Reliability:

Restored missing backend calls in the installation thread to ensure OpenCore is actually written to the EFI partition.

Fixed a logic bug where self.result wasn't being updated, which previously prevented the "Success" and "Reboot" prompts from appearing.

Python 3.13/3.14 Compatibility:

General code cleanup to support stricter object lifecycle management in newer Python environments.

## 3.0.0 alpha 11:
This release:
- Resolved RuntimeError: wrapped C/C++ object of type TextCtrl has been deleted in the Build Frame. This was achieved by implementing a finally block to ensure the ThreadHandler is explicitly removed from the global logger before the UI frame is destroyed, preventing race conditions during build-to-install transitions.

## 3.0.0 alpha 10 and 10S:
3.0.0 alpha 10 alongside 3.0.0 alpha 10S fixes the following issues:
- In updates.py, REPO_LATEST_RELEASE_URL was pointing to a web page. This bug affects all versions from 3.0.0 alpha 2 onwards.
- Fixes a bug in gui_build.py that prevents OpenCore EFIs from building.

Known issue:
- core.py panics as soon as trying to apply OpenCore EFIs and thus the app crashes

## 3.0.0 alpha 9
This release:
- Adds the special version of WhateverGreen that works with iBridged - but will not be injected automatically via OCLP until a future alpha release, just like the iBridged.kext. To inject these, first build the EFI via the OpenCore Legacy Patcher app as you would do noramlly, and then add those 2 kexts via OCAuxiliaryTools or ProperTree.
- Fixes a bug in logging_handler.py that makes the application less stable or outright to crash
- Now, when the OpenCore Legacy Patcher app crashes, it will show the error just like pre-alpha 5, so for example attackers can't unknowingly exploit vulnerabilities, for example - to crash the app and unknowingly to the user they execute malicious code. This bug affects this repository only. It's both a bug and a vulnerability.

To fix this vulnerability, update to the latest version available.

## 3.0.0 alpha 8:
This release will start enabling WhateverGreen.kext for unsupported T2 Macs to allow patching GPUs in the future - but only partially. And this release also fixes a vulnerability where when trying to build OpenCore EFI on unsupported T2 Macs, an attacker can prevent from building the EFI and execute arbitary code in the background unknowingly while to the user it shows an error only. This vulnerability affects this project only. This vulnerability was present since 3.0.0 alpha 1.

To fix this vulnerability, update to the latest version available.

## 3.0.0 alpha 7
This release adds:
- a very experimental version of iBridged to add T2 spoofing capabilities. This will allow booting into macOS 15 Sequoia and macOS 26 Tahoe, but for 26 Tahoe, at the release of iBridged 1.1.0b1 support is incomplete. The kext overall will see improvements in future alpha versions. It may have some bugs still pending to be fixed. The kext will not be automatically injected into OpenCore automatically yet, as it may be not fully stable yet. But for this to work, you need an SMBIOS of a unsupported or supported T2 Mac. On unsupported T2 Macs, you generally may not need SMBIOS spoofing to get it to work.
- All update links are changed from Dortania's original OpenCore Legacy Patcher to this repository, but the update infrastructure is not yet complete

This release also fixes the following vulnerabilities:
- sys.exit at OpenCore-Patcher-GUI.command was set 1 instead of 3. This allows attackers to crash the project to execute arbitary code and take advantage of other vulnerabilities without a human to realize. This vulnerability affects this repository only. Dortania's own is not affected by this.
- Updated follow-redirects dependency to resolve a security vulnerability (CVE-2024-28849). This prevents potential credential leakage during documentation build processes. This affects both this and Dortania's own repository.

To fix these vulnerabilities, update to the latest version available.

## 3.0.0 alpha 6
This release fixes the following:
- To Mac Pro 2019 users they were offered OpenCore EFIs for unsupported Macs, while the 2019 Mac Pro supports Tahoe natively
- On macOS 26 Tahoe Root Patching was greyed out - unblocking this feature allows any unsupported Macs to get root patches on macOS 26 Tahoe. But I have a big warning:  This project is focusing only on T2 Macs for now. On non-T2 Macs, their drivers on some Macs are full of memory corruption bugs, and macOS 26 Tahoe is very strict about this. macOS Tahoe blocks by default known vulnerable kexts by default, much more like Windows 11's Vulnerable Driver Blocklist. On macOS, disabling this is not as simple as in Windows 11 - on Windows 11, it's as easy as going to Windows Defender and disable the option for Vulnerable Driver Blocklist. On macOS, it's not like this. Also, many non-T2 Macs like the 2007-2009 Macs, had received their last update in 2018, which means their kexts are essentially frozen back in time. 

## 3.0.0 alpha 5
- fixes an issue that prevents from building the OpenCore into the disk - the fix is temporary and requires when building the EFI to enter the password inside the Terminal app
- fixes a bug where on T2 Macs it puts inside the EFI 2 Lilus and CryptexFixups.
- Removes requirements for Apple certificates

🛡️ Security & Hardening:
These vulnerabilities affect both this repository and Dortania's official repository.
Resolved Path Injection Vulnerability (CWE-427): Hardened the application entry point by stripping the current working directory from sys.path. This prevents the execution of malicious local scripts during app startup.

Internal Path Sanitization: Implemented generic error handling in the PyInstaller entry point to prevent leaking sensitive local system paths and usernames via Python tracebacks.

Privileged Execution Refactoring: Transitioned from a fixed Privileged Helper Tool binary to a dynamic sudo-based execution model, reducing dependencies on signed external binaries while maintaining system-level task capabilities.

When building the EFI, an attacker could write invalid synthax to crash the project, or worse - execute arbitary code. This is fixed by wrapping with try/except blocks.

## 3.0.0 alpha 4.3
- fixes an issue where OpenCore Legacy Patcher T2 won't open
- fixes an issue that prevents from building the OpenCore into the disk partially

## 3.0.0 alpha 4.2
- fixes a vulnerability where in constants.py the repository to check for updates was https://github.com/p8bpg9zrw7-collab/OpenCore-Legacy-Patcher-T2 - the old link. An attacker could redirect to a malicious GitHub repository or could launch a malicious redirect to install malware, for example AtomicStealer. This vulnerability affects versions from 3.0.0 alpha 2 all the way until 3.0.0 alpha 4.1.
## 3.0.0 alpha 4.1
- Fixed broken files that when uploading to GitHub they broke while uploading. This increases stability of the OpenCore Legacy Patcher T2 app.
- Changed the GitHub repository to a clean repo to clean the mess of broken files.
- Removed the iBridged.kext to clean broken files. I'm planning to readd these soon.

## 3.0.0 alpha 4
- Switch KDK comments and messages from Chinese to English
- Now iBridge's source code is no longer stored in a zip file, so you can read it at any time

## 3.0.0 alpha 3
- This version patches a security vulnerability in the networking library that could have allowed for insecure connections when downloading macOS assets or patches. (Updated requests to 2.32.2). This vulnerability affects both this repository and Dortania's official OpenCore Legacy Patcher repository. To address this vulnerability, update to the latest available release.

## 3.0.0 alpha 2
- Now it will always check for updatees from our repository instead of Dortania's
- Bug fixes in OpenCore Legacy Patcher T2 prevents from flashing the OpenCore bootloader, regardless of the Mac model.
- Add the original source code of iBridged.kext, which requires some work to fix its vulnerabilities.

## 3.0.0 alpha 1
- Add partial support for unsupported T2 Macs

## 3.0.0 (initial release of the official OpenCore Legacy Patcher 3.0.0)
- Restore support for FileVault 2 on macOS 26
- Add USB mappings for macOS 26
- Adopt Liquid Glass-conformant app icon
- Increment Binaries:
  - OpenCorePkg 1.0.5 - rolling (f03819e)

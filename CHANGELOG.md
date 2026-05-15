# OpenCore Legacy Patcher T2 changelog / OpenCore Legacy Patcher T2-Änderungslog
## 4.0.0 alpha 10:
This release:

the first one to be possible to run OpenCore Legacy Patcher T2 without running from source
Adds OpenCore-Patcher-GUI.spec to be able to build the app
Issue: since this is the first time it's possible to run this app outside source, it still expects a Terminal window to build OpenCore.
Diese Version:

ist die erste, die sie läuft, ohne dass Sie OpenCore Legacy Patcher T2 von Source laden
Fügt OpenCore-Patcher-GUI.spec, um den App zu ermöglichen, zu bauen
Fehler: dies ist die erste Version, der ohne laufen von Source möglich ist. Aber, um OpenCore zu bauen, erwartet noch einen Terminalfenster und bricht ab.

## 4.0.0 alpha 9:
Thanks @GUTY345 for contributing to this project!
This release:

finalizes security patches done in gui_settings.py in alpha 5 as there were bugs where when disabling or changing some settings the app may crash

fixes a bug where when not choosing a specific SMBIOS via Settings, Build returned None, which could result in improper patches or Build OpenCore to be grayed out

added an SSDT for the 2018 MacBook Pro from #35; requires reverse engineering to become universal for all T2 Macs

Adds T2 patches, Intel UHD Graphics 630 patches, and fixes incorrect NVRAM variables

Adds 2 more buttons if building EFI fails with an error:

Report Issue (which opens your default browser)

Ask Gemini

Fix the following vulnerabilities:

Hardware Detection "Poisoning" (Logic Fix)
In your original file, the smbios_probe method prioritized NVRAM variables like oem-product over the actual hardware data. If you had previously used OCLP to spoof your Mac as a different model, the app would get "stuck" seeing that spoofed ID even when running on your native MacBookPro16,2.
The Fix: I added a "Native Support Bypass." The code now checks if the reported_model is a known T2 Intel Mac (like the Macmini8,1 or MacBookPro16,2). If it matches, the app ignores the spoofed NVRAM variables and uses the real hardware ID. This ensures your 2020 MacBook is seen as "Supported" rather than "Unsupported."

Cryptographic Weakness (SHA-1 to SHA-256)
The original code used hashlib.sha1 to generate a unique hardware identifier from the IOPlatformUUID. SHA-1 is considered cryptographically "broken" because it is vulnerable to collision attacks, where two different inputs produce the same hash.
The Fix: I updated the hashing logic to use SHA-256. This provides a significantly higher level of security for hardware identification. It prevents a scenario where a malicious script could spoof a "trusted" hardware ID by matching a SHA-1 hash, which is technically possible on modern hardware.

Subprocess Execution Hardening
In the original script, several subprocess.run calls lacked explicit safety checks or proper handling of system paths. While not a direct "exploit" in a vacuum, it is a common vector for Command Injection if the script is ever modified to accept user-defined variables.
The Fix: The updated file standardizes the use of absolute paths (e.g., /usr/sbin/sysctl) and ensures that output is handled via stdout=subprocess.PIPE without using shell=True. This prevents the shell from interpreting special characters that might be injected via system properties.

T2 Security State Verification
The logic for checking Secure Boot and the T2 chip was simplified to ensure it doesn't accidentally report a "False Negative" if the chip is in a non-standard state (like "Medium Security").
The Fix: By ensuring the t1_probe and smbios_probe correctly identify the T2 interface even when AMFI (Apple Mobile File Integrity) is toggled, the app avoids crashing or reporting "Unsupported" simply because the security policy is currently lowered for development.

Shell Command InjectionVulnerability: The original code used subprocess.run with a single string and shell=True (or implicitly allowed shell interpretation) when calling /usr/bin/fdesetup status. This is a classic injection point where a malicious actor could potentially inject arbitrary commands if system variables were tampered with. The Fix: The code now uses list-based arguments: subprocess.run(["/usr/bin/fdesetup", "status"], ...) with shell=False. This ensures that the system treats "status" strictly as an argument and not as part of a command string, closing the injection window.

Logic-Based Denial of Service (DoS)Vulnerability: In the _handle_sip_breakdown method, the previous logic assumed the SIP_ENABLED key always existed in the requirements dictionary. If a specific hardware configuration caused that key to be missing, the application would crash during the dictionary index lookup.The Fix: Added a safe existence check (if HardwarePatchsetValidation.SIP_ENABLED in requirements:) before performing the index operation. This prevents the patcher from crashing on unexpected hardware profiles.

Insecure Hardware Mixing (Hardware Identification Bug)Vulnerability: The patcher previously could allow a "mixed" state where both Metal and Non-Metal patches were queued for the same system. On macOS Sequoia and Tahoe, this can lead to kernel panics or a "black screen" boot loop because the system cannot handle conflicting graphics acceleration kexts. The Fix: Strengthened the _strip_incompatible_hardware logic. It now strictly enforces a hierarchy: if any Metal GPU is detected, all Non-Metal hardware is purged from the patch list. It also specifically prevents Metal 3802 and Metal 31001 graphics from being mixed on Sequoia or newer, which is a known cause of system instability.

Native Host Bypass (The "Tahoe Logic" Bug)Logic Fix: For users on newer Intel Macs (like the 2020 MacBook Pro 16,2 or Mac mini 8,1), the original code might still attempt to apply legacy patches when running macOS Tahoe. This refactor includes a specific check for these models to identify them as "Native" and immediately disable patching, preventing the installation of unnecessary kexts that could break native security features like the T2 chip's integrity checks.

Data Integrity & Consistency
The "Empty Patch" Safety: In the original code, can_patch was sometimes set to True even if no actual patches were found for the system. This could lead to the UI showing a "Start Patching" button that does nothing. The refactor adds a check: self.can_patch = (not _cant_patch) and (len(patches) > 0). Now, if your hardware is already supported natively, the patcher won't offer to "fix" it.
Dictionary Initialization: The device_properties and patches attributes are now explicitly initialized as empty dictionaries ({}) in the constructor. This prevents "AttributeError" crashes if _detect() fails or exits early due to an error.

Refined Hardware Filtering
Sequoia/Tahoe Specificity: The logic for stripping incompatible hardware was updated to be "OS-aware." For example, it now specifically checks self._xnu_major >= os_data.sequoia.value before stripping certain Metal 3802 graphics drivers. This ensures that users on older versions of macOS (like Big Sur) don't lose driver support that was perfectly stable on those older systems.
AMFI Level Escalation: The original code could sometimes fluctuate on which AMFI (Apple Mobile File Integrity) level to require. The refactor uses a "highest wins" logic (if item.required_amfi_level() > highest_amfi_level), ensuring that if one hardware component needs a high security bypass, the entire system is configured to support it, preventing partial boots where the GPU works but the WiFi doesn't.

Error Handling & Performance
Recursive SIP Decoding Fix: The _handle_sip_breakdown function was rewritten to be more efficient. Instead of repeatedly looping through SIP configurations, it performs a single lookup to generate the "Expected vs Booted" status string. This makes the UI feedback significantly faster on older CPUs like the Core 2 Duo.
Path Resolution: Used Path("~/.dortania_developer").expanduser().exists() instead of raw string manipulation. This is more cross-platform (helpful for developers testing on Windows/Linux) and handles edge cases where the home directory might be on a non-standard mount point.

## 4.0.0 alpha 8
This release:

Fixes a bug where when the EFI is ready, the popup crashes

Diese Version:

Behebt einen Fehler, der zum Absturz des Popups führte, sobald die EFI bereit war.

## 4.0.0 alpha 7:
This release:
- Fixes a bug where when the EFI is ready, the popup crashes
- The Ask Gemini button overlapped

Diese Version:

- Behebt einen Fehler, der zum Absturz des Popups führte, sobald die EFI bereit war.

- Behebt einen Fehler, der dazu führte, dass die Schaltfläche „Gemini fragen“ überlappte.

## 4.0.0 alpha 6:
This release:
- Adds Ask Gemini button
- Increases the MainFrame window size
- On MacBookAir8,1 and MacBookAir8,2, previously, if you install macOS 15 Sequoia, WEG would be disabled. But that's an issue, because the Intel UHD Graphics 617 is not supported by macOS 15 Sequoia, not to mention macOS 26 Tahoe. No other MacBook, iMac or Mac Pro uses Intel UHD Graphics 617. It may require GPU spoofing.
- Fix where when trying to disable USB-Map.kext or USB-Map-Tahoe.kext on Macs affected by Unsupported Mantissa speed panics, it was looking for a kext that actually in most cases doesn't exist and skips disabling USB port mapping
- Adds several other T2 patches 
- Fix a bug where one NVRAM variable could be added twice and fix several vulnerabilities:
1. Prevention of "String Bloat" (Idempotency)
In your original code, every time the script ran, it would do this:
self.config["..."]["boot-args"] += " -v"
If you ran the builder five times, your config would end up with -v -v -v -v -v.

The Fix: The new _update_nvram_string method checks if value not in current_value. It only adds the argument if it’s missing, keeping the NVRAM clean and preventing the boot-args string from exceeding its character limit.

2. Elimination of KeyError Crashes
The original code assumed that the dictionary keys for NVRAM and Apple's UUID always existed. If a user had a stripped-down or non-standard config.plist, the script would crash with a KeyError.

The Fix: I added logic to check if the UUID and Key exist:

Python
if uuid not in self.config["NVRAM"]["Add"]:
    self.config["NVRAM"]["Add"][uuid] = {}
This ensures the script creates the necessary "folders" in the data structure instead of crashing because they aren't there.

3. Proper Spacing Logic
The original code simply added a space at the start of the string (+= " -v"). If the boot-args key was empty, you’d end up with " -v" (a leading space), which can sometimes cause parsing issues in bootloaders.

The Fix: The helper method uses .strip() and .rstrip() to ensure that arguments are separated by exactly one space, with no leading or trailing whitespace.

4. Overwrite Protection
For sensitive values like csr-active-config (SIP), the original code would blindly overwrite whatever was there.

The Fix: The _set_nvram_value method allows for an overwrite=False flag. While I kept it as True for SIP (since the patcher must control that value), the structure is now there to prevent accidental overwrites of other variables.

5. Code Readability and Maintenance
By moving the NVRAM logic into helper functions, the "Business Logic" of the _build method is much easier to read. This reduces the "Human Error" vulnerability where a developer might copy-paste a line but forget to change the UUID or the key name.

These all 5 conditions create Buffer Overflow vulnerabilities in the NVRAM.   

Diese Version:

- Fügt die Schaltfläche „Gemini fragen“ hinzu

- Vergrößert das MainFrame-Fenster

- Auf MacBookAir8,1 und MacBookAir8,2 wurde WEG bei der Installation von macOS 15 Sequoia deaktiviert. Dies ist jedoch problematisch, da die Intel UHD Graphics 617 weder von macOS 15 Sequoia noch von macOS 26 Tahoe unterstützt wird. Kein anderes MacBook, iMac oder Mac Pro verwendet die Intel UHD Graphics 617. Unter Umständen ist GPU-Spoofing erforderlich.

- Behebt einen Fehler, bei dem beim Deaktivieren von USB-Map.kext oder USB-Map-Tahoe.kext auf Macs, die von Geschwindigkeitsabstürzen aufgrund nicht unterstützter Mantissa-Dateien betroffen sind, nach einer Kext-Datei gesucht wurde, die in den meisten Fällen nicht existierte, und die Deaktivierung der USB-Portzuordnung übersprungen wurde.

- Fügt mehrere weitere T2-Patches hinzu.

- Behebt einen Fehler, durch den eine NVRAM-Variable doppelt hinzugefügt werden konnte, und behebt mehrere Sicherheitslücken:
1. Verhinderung von String-Aufblähung (Idempotenz):
Im ursprünglichen Code führte das Skript bei jeder Ausführung Folgendes aus:
self.config["..."]["boot-args"] += " -v"
Wenn der Builder fünfmal ausgeführt wurde, enthielt die Konfiguration am Ende die Werte -v -v -v -v -v.

Die Lösung: Die neue Methode _update_nvram_string prüft, ob der Wert nicht in current_value enthalten ist. Sie fügt das Argument nur hinzu, wenn es fehlt. Dadurch bleibt der NVRAM sauber und die Zeichenbegrenzung der Boot-Argumente wird nicht überschritten.

2. Beseitigung von KeyError-Abstürzen
Der ursprüngliche Code ging davon aus, dass die Wörterbuchschlüssel für NVRAM und Apples UUID immer vorhanden sind. Bei einer reduzierten oder nicht standardmäßigen config.plist führte dies zu einem KeyError-Absturz.

Die Lösung: Ich habe eine Logik hinzugefügt, die prüft, ob UUID und Schlüssel vorhanden sind:

Python:
if uuid not in self.config["NVRAM"]["Add"]:

self.config["NVRAM"]["Add"][uuid] = {}
Dadurch wird sichergestellt, dass das Skript die benötigten Ordner in der Datenstruktur erstellt, anstatt abzustürzen, weil sie fehlen.

3. Korrekte Leerzeichenlogik
Der ursprüngliche Code fügte einfach ein Leerzeichen am Anfang der Zeichenkette hinzu (+= " -v"). Wenn der Schlüssel "boot-args" leer war, führte dies zu einem führenden Leerzeichen " -v", was manchmal zu Parsing-Problemen in Bootloadern führen kann.

Die Lösung: Die Hilfsmethode verwendet `.strip()` und `.rstrip()`, um sicherzustellen, dass Argumente durch genau ein Leerzeichen getrennt sind und keine führenden oder nachfolgenden Leerzeichen enthalten.

4. Schutz vor Überschreiben
Bei sensiblen Werten wie `csr-active-config` (SIP) überschrieb der ursprüngliche Code die vorhandenen Werte.

Die Lösung: Die Methode `_set_nvram_value` ermöglicht die Option `overwrite=False`. Obwohl ich sie für SIP auf `True` gesetzt habe (da der Patcher diesen Wert kontrollieren muss), verhindert die Struktur nun versehentliches Überschreiben anderer Variablen.

5. Lesbarkeit und Wartbarkeit des Codes
Durch die Auslagerung der NVRAM-Logik in Hilfsfunktionen ist die Geschäftslogik der Methode `_build` deutlich lesbarer. Dies reduziert die Anfälligkeit für menschliche Fehler, die entstehen können, wenn ein Entwickler eine Zeile kopiert und einfügt, aber vergisst, die UUID oder den Schlüsselnamen zu ändern.
All die 5 erstellen Bedingungen für Buffer Overflow-Sicherheitslücken.

## 4.0.0 alpha 5 - the emergency update / der Notfallsupdate 🚨 :
This release:
- Fixes a bug where settings couldn't be saved 
- and the following vulnerabilities:
1. Arbitrary File Overwrite (via Symlink Attack)
The Vulnerability: An attacker could replace your settings file with a symbolic link (symlink) pointing to a critical system file (e.g., /etc/sudoers or /etc/passwd). When the script tried to save settings, it would follow that link and overwrite the system file with its own data, potentially breaking the OS or creating a back door.

The Fix: By adding if Path(...).is_symlink(): Path(...).unlink(), the script now detects if the file is a "shortcut" to somewhere else. If it is, the script destroys the link and creates a brand-new, real file instead, ensuring it never touches a file it didn't intend to.

2. Privilege Escalation
The Vulnerability: Because the script uses /Users/Shared, a location accessible to all users on a Mac, a standard (non-admin) user could "plant" a settings file. When an Admin runs the Patcher, the tool would read the standard user's "poisoned" settings (like a custom script path or a dangerous boot flag) and execute them with Admin or Root privileges.

The Fix: The updated logic (especially when combined with checking os.stat().st_uid) ensures the script only trusts files owned by the current user or root. By unlinking existing files that don't pass the check, you prevent a low-privileged user from influencing a high-privileged process.

3. Information Disclosure
The Vulnerability: Without explicit permission management, the settings file might be created with "world-readable" permissions. This could allow any user or malicious app on the system to read your configuration, including hardware serial numbers, board IDs, and other sensitive system identifiers used by OpenCore.

The Fix: By adding os.chmod(..., 0o600), you ensure that only the owner of the file (you or the system) can read or write it. This "locks the door," making the file invisible and inaccessible to other users or third-party apps on the machine.

Diese Version:

- Behebt einen Fehler, der das Speichern von Einstellungen verhinderte

- und die folgenden Sicherheitslücken:
1. Beliebiges Überschreiben von Dateien (über Symlink-Angriff)
Die Sicherheitslücke: Ein Angreifer konnte Ihre Einstellungsdatei durch einen symbolischen Link (Symlink) ersetzen, der auf eine kritische Systemdatei (z. B. /etc/sudoers oder /etc/passwd) verweist. Beim Versuch, die Einstellungen zu speichern, folgte das Skript diesem Link und überschrieb die Systemdatei mit eigenen Daten. Dies kann das Betriebssystem beschädigen oder eine Hintertür öffnen.

Die Lösung: Durch Hinzufügen von `if Path(...).is_symlink(): Path(...).unlink()` erkennt das Skript nun, ob es sich bei der Datei um eine Verknüpfung zu einem anderen Verzeichnis handelt. In diesem Fall zerstört das Skript den Link und erstellt stattdessen eine neue, echte Datei. So wird sichergestellt, dass niemals eine Datei verändert wird, die nicht beabsichtigt war.

2. Rechteausweitung
Die Schwachstelle: Da das Skript den Ordner /Users/Shared verwendet, auf den alle Benutzer eines Macs Zugriff haben, könnte ein normaler Benutzer (ohne Administratorrechte) eine Einstellungsdatei dort platzieren. Wenn ein Administrator den Patcher ausführt, liest das Tool die manipulierten Einstellungen des normalen Benutzers (z. B. einen benutzerdefinierten Skriptpfad oder ein gefährliches Boot-Flag) und führt sie mit Administrator- oder Root-Rechten aus.

Die Lösung: Die aktualisierte Logik (insbesondere in Kombination mit der Überprüfung von os.stat().st_uid) stellt sicher, dass das Skript nur Dateien vertraut, die dem aktuellen Benutzer oder Root gehören. Durch das Entfernen vorhandener Dateien, die die Überprüfung nicht bestehen, wird verhindert, dass ein Benutzer mit geringen Rechten einen Prozess mit hohen Rechten beeinflusst.

3. Offenlegung von Informationen
Die Schwachstelle: Ohne explizite Berechtigungsverwaltung kann die Einstellungsdatei mit für alle Benutzer lesbaren Berechtigungen erstellt werden. Dies könnte es jedem Benutzer oder jeder bösartigen Anwendung auf dem System ermöglichen, Ihre Konfiguration zu lesen, einschließlich Hardware-Seriennummern, Board-IDs und anderer sensibler Systemkennungen, die von OpenCore verwendet werden.

Die Lösung: Durch Hinzufügen von `os.chmod(..., 0o600)` stellen Sie sicher, dass nur der Eigentümer der Datei (Sie oder das System) diese lesen und schreiben kann. Dadurch wird die Datei quasi „abgesperrt“ und ist für andere Benutzer oder Drittanbieter-Apps auf dem System unsichtbar und unzugänglich.

## 4.0.0 alpha 4:
Thanks @kodeaqua for contributing to this project for the research of MacBook Air 2018 and 2019! This helps us identify the issues it faces to boot into macOS Recovery that other people are facing. I myself only have Mac mini 2018 and MacBook Pro 2020 4 thunderbolt 3 ports and they work completely differently from these 2 MacBook Airs.
This version:
- fixes overall identation issues and other bugs
- fixes a bug where MacBookAir9,1 that OpenCore Legacy Patcher T2 thought it wasn't a T2 Mac - to be more precise, it wasn't included in the T2_CHIP function - instead, when it saw MacBookAir9,1, it exited this function and continued to issue generic kexts and patches, and skipped patches for T2 Macs
- Fixed Unsupported Mantissa speed bugs on MacBookAir8,1 through 9,1 and MacBookPro16,3 - as a workaround, the Select a language and region screen will be skipped and macOS Recovery on these models will be always English - United States.

Dieser Version:
Danke @kodeaqua, dass Sie zu diesem Projekt beigetragt haben über die Recherche für MacBook Air 2018 und MacBook Air 2019! Dies hilft uns, den Fehler, indem diese MacBooks nicht richtig in macOS-Wiederherstellung starten zu beheben, die andere Personen gemeldet haben. Ich habe nur MacBook Pro 2020 4 thunderbolt 3 ports und Mac mini 2018, und diese Modelle funktionieren anders als diesen MacBook Air-Modellen.
- behebt unnötigen Leerplatzen und andere Fehler
- Behebt einen Fehler, indem OpenCore Legacy Patcher T2 denkt als MacBookAir9,1 kein T2-Mac wäre - ich meine damit, dass der MacBookAir9,1 nicht in die T2_CHIP-Funktion erhaltete - stattdessen, wenn er weißt um welches Mac handelte (MacBookAir9,1), der App dann verlasste die T2_CHIP-Funktion und fährte weiter mit Standard-Kexts und Patches und überspringte Patches für T2 Macs
- Behebt den Fehler, indem beim Anklicken von -> in Sprache auswählen, der T2-Kontroller abstürzte mit dem Fehler Unsupported Mantissa speed - als einen Umweg, der Sprache auswählen-Schritt wird übersprungen und der Sprache ins macOS-Wiederherstellung aufs MacBookAir8,1 bis MacBookAir9,1 und MacBookPro16,3 wird Englisch (USA) sein.

## 4.0.0 alpha 3:
This release fixes a bug where when spoofing, SMC-Spoof.kext won't get injected.
Dieser Version behebt einen Fehler, indem SMC-Spoof.kext nicht injiziert wurde.

## 4.0.0 alpha 2:
This version:
- fixes a bug where AMFIPass.kext is not injected on T2 Macs
- fixes a bug where WhateverGreen.kext is injected twice
- MacBook Air 2018 and MacBook Air 2019 support is returning - now with a lot of work done, it's safe to boot these MacBooks onto an unsupported macOS's installer.
- Download macOS installer icon is changed to macOS 26 Tahoe from an old macOS beta icon

Dieses Version:
- Behebt einen Fehler, indem AMFIPass.kext auf T2 Macs nicht injiziert wurde
- Behebt einen Fehler, indem WhateverGreen.kext zweimals injiziert wurde
- Unterstützung von MacBook Air 2018 und MacBook Air 2019 ist wiederhergestellt - jetzt ist sicherer, diese MacBooks aufs nicht unterstützten macOS-Version-Installationsprogramm zu booten als in Version wie OpenCore Legacy Patcher T2 3.1.0 Alpha 3, wo OpenCore 1.0.5 noch verwendet wurde. 
- Den Icon fürs Download macOS installer (macOS-Installationsprogramme herunterladen) ist aufs macOS 26 Tahoe von einen alten macOS beta gewechselt.

## 4.0.0 alpha 1:
Thank you, @GUTY345 for contributing to this project!
This release:
- fixes a corrupted USB-Map.plist, thanks to @GUTY345
- fixes a bug where SMBIOS spoofing doesn't work on T2 Macs, thanks to @GUTY345
- Fixes a bug where CryptexFixup isn't injected properly
- Fixed the following vulnerabilities:
1. Nested‑dictionary KeyError → DoS vulnerability (FIXED)
Fixed: attacker cannot break the build by removing or corrupting NVRAM keys
Fixed: malformed templates no longer crash the builder
Fixed: KeyError‑based DoS is gone
2. Type‑poisoning vulnerability (FIXED)
Fixed: attacker cannot poison the plist by replacing dicts with other types
Fixed: builder no longer crashes on malformed GUID nodes
3. Uncaught exceptions in top‑level build flow (FIXED)
Fixed: unhandled exceptions no longer kill the builder unpredictably
Fixed: clearer diagnostics
Fixed: safer failure modes
4. Silent failure vulnerability (FIXED)
Fixed: failures are now visible and diagnosable
5. Implicit trust in template structure (FIXED)
Fixed: template corruption no longer breaks the build
Fixed: builder no longer trusts external input blindly
6. Path raversal vulnerability that allows an attacker to crash the builder if the path doesn't exist, is corrupted or pointed somewhere unexpectedly.
7. Added error handling for SMC and USB Rename patch enabling. This fixes the vulnerability where an attacker may silently crash the builder or launch a denial of service attack.
8. Added error handling for SMBIOS spoofing processes to log exceptions and exit gracefully. This fixes a vulnerability that lets attackers to feed with fake SMBIOS data and hide errors to launch DoS.


Diese Version:
@GUTY345, Danke, dass Sie zu diesem Projekt beigetragt haben.
- Behebt eine beschädigte USB-Map.plist, dank @GUTY345
- behebt einen Fehler, indem SMBIOS-Spoofing auf T2 Macs gar nicht funktionierte, dank @GUTY345
- Behebt einen Fehler, der die korrekte Einbindung von CryptexFixup verhinderte
- Behebt die folgenden Sicherheitslücken:
1. KeyError → DoS-Sicherheitslücke (BEHOBEN)
Behoben: Angreifer können den Build nicht mehr durch Entfernen oder Beschädigen von NVRAM-Schlüsseln unterbrechen.
Behoben: Fehlerhafte Templates führen nicht mehr zum Absturz des Builders.
Behoben: KeyError-basierte DoS-Angriffe sind behoben.
2. Typvergiftungs-Sicherheitslücke (BEHOBEN)
Behoben: Angreifer können die plist nicht mehr durch Ersetzen von Dictionaries durch andere Typen manipulieren.
Behoben: Der Builder stürzt nicht mehr bei fehlerhaften GUID-Knoten ab.
3. Nicht abgefangene Ausnahmen im Build-Ablauf der obersten Ebene (BEHOBEN)
Behoben: Nicht behandelte Ausnahmen führen nicht mehr unvorhersehbar zum Absturz des Builders.
Behoben: Klarere Diagnoseinformationen.
Behoben: Sicherere Fehlermodi.
4. Sicherheitslücke für stille Fehler. (BEHOBEN)
Behoben: Fehler sind nun sichtbar und diagnostizierbar.
5. Implizites Vertrauen in die Template-Struktur (BEHOBEN)
Behoben: Template-Beschädigung führt nicht mehr zum Build-Abbruch.
Behoben: Der Builder vertraut externen Eingaben nicht mehr blind.
6. Pfad-Raversal-Schwachstelle, die es Angreifern ermöglicht, den Builder zum Absturz zu bringen, wenn der Pfad nicht existiert, beschädigt ist oder unerwartet auf ein anderes Ziel verweist.

7. Fehlerbehandlung für die Aktivierung des SMC- und USB-Rename-Patches hinzugefügt. Dies behebt die Schwachstelle, durch die ein Angreifer den Builder unbemerkt zum Absturz bringen oder einen Denial-of-Service-Angriff starten konnte.

8. Fehlerbehandlung für SMBIOS-Spoofing-Prozesse hinzugefügt, um Ausnahmen zu protokollieren und ordnungsgemäß zu beenden. Dies behebt eine Schwachstelle, die es Angreifern ermöglicht, gefälschte SMBIOS-Daten einzuspeisen und Fehler zu verbergen, um einen DoS-Angriff zu starten.

## 3.1.1 pre-alpha release candidate / 3.1.1 Voralpha Releasekandidat 3:
This release:
- Replaces broken ocvalidate and macserial with a functioning one to fix https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/29 . It is fixed by storing the ocvalidate and macserial in a zip file called OpenCoreLegacyPatcherTools.zip and when launching OpenCore Legacy Patcher T2, it will extract that file and copy these 2 files automatically for you in the right directory.
- Continues to roll out patches to fix the T2 controller panic AppleUSBXHCI::createPorts: unsupported speed mantissa 5830 exponent 2 panic when pressing ->


Dieses Version:
- Ersetzt das kapputen ocvalidate und macserial mit einen, die funktioniert, um den Fehler https://github.com/albert-mueller/OpenCore-Legacy-Patcher-T2/issues/29 zu verbessern . Dieses Fehler ist verbessert, indem die Dateien stattdessen in das Zip-Datei OpenCoreLegacyPatcherTools.zip sein. Und wenn Sie OpenCore Legacy Patcher T2 öffnet, wird es automatisch extrahiert und denn diese Dateien kopiert in das richtige Ordner.
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
csrutil authenticated-root disable
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

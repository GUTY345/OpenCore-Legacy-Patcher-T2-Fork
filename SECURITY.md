# Security Policy

## Fork and project naming (doesn't apply to forks forked directly through the GitHub interface)
Forks when naming their projects, they shouldn't put misleading names such as OCLP-T2, OpenCоrе-Legacy-Patcher-T2 (with cyrillic o and e) or OpenCore-Legacy-Patcher-2-2. This is an example of typosquatting:
<img width="1712" height="910" alt="image" src="https://github.com/user-attachments/assets/cce043f6-90bd-478a-a4dd-edab048cb79e" />

This is considered typosquatting. If typosquatted, one of the following actions may take place:
1. Scan the fork for malware (e.g looking for malware in the source code, test it inside a virtual machine or sandbox) by the developer of the main project (Albert Müller)
2. If none is found, the developer of the main project (Albert Müller) may open up an issue requesting to rename the project
3. If the project is confirmed malicious, the main developer (Albert Müller) may report directly to GitHub

This applies only to forks uploading their forks as projects instead of clicking the Fork button. When clicking the Fork button, by default the name is OpenCore Legacy Patcher T2 and these are less visible in the internet and harder for attackers even to pull off the attack.

## Up to date Versions

Ensure you are running one of the latest up-to-date versions:

| Version | Latest version          |
| ------- | ------------------ |
| 4.0.0 pre-alpha for alpha 16| :white_check_mark: |

Version 3.1.1 and older are completely unsupported since May 8 2026. No technical support will be provided to anyone including forks that are using versions this old. Some projects may claim they are using 4.0.0 alpha 1 or 4.0.0 alpha 15 while they are using modified 3.0.0 alpha 4.1 without patching the associated vulnerabilities - watch out for these - for these forks, no technical support will be provided as well. How to understand if the version is spoofed?
1. Click on for example 9 commits or the number of commits that this fork did
<img width="1712" height="910" alt="Bild 16 07 26 um 18 05" src="https://github.com/user-attachments/assets/7e971f1f-65e2-4c99-b0a9-b2c0f8b0999d" />
2. Check for commit history - 9 commits and then update constants.py to version 4.0.0 alpha 1 or alpha 15 is suspicious unless they pushed a pull request to their repository.
Example of version spoofing:
<img width="1712" height="910" alt="image" src="https://github.com/user-attachments/assets/f114a2e9-a41a-40b6-a8dc-aad2a20bb1d4" />

## Reporting a Vulnerability

We strongly encourage using **Private Vulnerability Reporting** to disclose security issues to maintainers securely and privately.

### How to report:
1. Navigate to the **Security** tab of the repository.
2. Click the **Report a vulnerability** button.
3. Provide all necessary details and a Safe Proof of Concept (PoC) that does not contain or distribute real malware. A safe PoC should trigger a harmless behavior, for example creating a folder/file on the desktop or showing logs.

### Out-of-Scope Reports:
**Do not** report disabling SIP (System Integrity Protection) or AMFI (Apple Mobile File Integrity) as vulnerabilities. These are necessary components for bypassing minimum system requirements and will be dismissed.

Note:
If it is a fork of this project, then enabling the Report a vulnerability button is up to the maintainer of the fork. In case they don't enable this button, open an Issue with a [Vulnerability] tag.
And forks may have different timeline on fixing certain vulnerabilities.

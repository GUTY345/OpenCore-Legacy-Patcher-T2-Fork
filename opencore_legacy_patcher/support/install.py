"""
install.py: Installation of OpenCore files to ESP
"""

import os
import logging
import plistlib
import subprocess
import re
import sys  # FIX: Wichtig für sys.exit() bei kritischen Fehlern
from pathlib import Path

from . import utilities, subprocess_wrapper
from .. import constants


class tui_disk_installation:
    def __init__(self, versions):
        self.constants: constants.Constants = versions

    @staticmethod
    def _is_efi_partition(partition: dict) -> bool:
        """Recognize only an EFI/FAT EFI System Partition reported by diskutil."""
        filesystem = str(partition.get("fs", "")).strip().lower()
        content = str(partition.get("type", "")).strip().lower()
        return filesystem in {"msdos", "efi"} or content in {"efi", "efi system partition"}

    def list_disks(self):
        all_disks = {}
        # TODO: AllDisksAndPartitions wird in Snow Leopard und älter nicht unterstützt
        try:
            # High Sierra und neuer
            disks = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "list", "-plist", "physical"], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        except ValueError:
            # Sierra und älter
            disks = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "list", "-plist"], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        
        for disk in disks["AllDisksAndPartitions"]:
            try:
                disk_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", disk["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip().encode())
            except Exception:
                # "Chinesium" USB-Sticks können korrupte Daten im MediaName Feld haben
                diskutil_output = subprocess.run(["/usr/sbin/diskutil", "info", "-plist", disk["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip()
                # FIX: flags=re.DOTALL hinzugefügt, damit Zeilenumbrüche im XML mitgematcht werden
                ungarbafied_output = re.sub(r'(<key>MediaName</key>\s*<string>).*?(</string>)', r'\1\2', diskutil_output, flags=re.DOTALL).encode()
                try:
                    disk_info = plistlib.loads(ungarbafied_output)
                except Exception:
                    # Falls das Laden immer noch fehlschlägt, überspringen wir die Disk, um Abstürze zu verhindern
                    continue
            
            try:
                all_disks[disk["DeviceIdentifier"]] = {"identifier": disk_info["DeviceNode"], "name": disk_info.get("MediaName", "Disk"), "size": disk_info["TotalSize"], "partitions": {}}
                for partition in disk["Partitions"]:
                    partition_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", partition["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip().encode())
                    filesystem_type = partition_info.get("FilesystemType") or partition_info.get("Content", "")
                    all_disks[disk["DeviceIdentifier"]]["partitions"][partition["DeviceIdentifier"]] = {
                        "fs": filesystem_type,
                        "type": partition_info["Content"],
                        "name": partition_info.get("VolumeName", ""),
                        "size": partition_info["TotalSize"],
                    }
            except KeyError:
                # Verhindert Abstürze, wenn z. B. CDs/DVDs eingelegt sind
                continue

        supported_disks = {}
        for disk in all_disks:
            if not any(self._is_efi_partition(all_disks[disk]["partitions"][partition]) for partition in all_disks[disk]["partitions"]):
                continue
            supported_disks.update({
                disk: {
                    "disk": disk,
                    "name": all_disks[disk]["name"],
                    "size": utilities.human_fmt(all_disks[disk]['size']),
                    "partitions": all_disks[disk]["partitions"]
                }
            })
        return supported_disks

    def list_partitions(self, disk_response, supported_disks):
        disk_identifier = disk_response
        
        # FIX: Sicherheitsprüfung, falls die Festplatte nicht (mehr) existiert
        selected_disk = supported_disks.get(disk_identifier)
        if not selected_disk:
            logging.error(f"Ausgewählte Festplatte {disk_identifier} wurde nicht gefunden.")
            logging.error(f"The selected disk {disk_identifier} wasn't found.")
            return {}

        supported_partitions = {}
        for partition in selected_disk["partitions"]:
            if not self._is_efi_partition(selected_disk["partitions"][partition]):
                continue
            supported_partitions.update({
                partition: {
                    "partition": partition,
                    "name": selected_disk["partitions"][partition]["name"],
                    "size": utilities.human_fmt(selected_disk["partitions"][partition]["size"])
                }
            })
        return supported_partitions

    def _determine_sd_card(self, media_name: str):
        if any(x in media_name for x in ("SD Card", "SD/MMC", "SDXC Reader", "SD Reader", "Card Reader")):
            return True
        return False

    @staticmethod
    def _run_esp_file_op(command: list, mount_path: Path) -> subprocess.CompletedProcess:
        """
        Execute a filesystem operation against the mounted ESP using the least
        privilege that actually works on this macOS version.

        macOS 15 Sequoia and newer serve msdos / EFI System Partitions through
        FSKit in the console user's security session. Such a mount is owned by
        and writable to the current user, while a command elevated via
        osascript/root runs in a *different* session that FSKit rejects with
        EPERM ("Operation not permitted") — this is what left the ESP empty.

        So when the mount point is writable by the current user we run the
        operation unprivileged; only on a traditional root-owned mount (older
        macOS) do we fall back to root. The result is verified so a failed copy
        raises loudly instead of silently producing an empty EFI.
        """
        if os.access(mount_path, os.W_OK):
            result = subprocess_wrapper.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            result = subprocess_wrapper.run_as_root(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess_wrapper.verify(result)
        return result

    def install_opencore(self, full_disk_identifier: str):
        # TODO: Apple Script schlägt in Yosemite und älter fehl
        logging.info(f"Mounte Partition: {full_disk_identifier}")
        logging.info(f"Mounting partition: {full_disk_identifier}")
        
        # Mount-Versuch als Root
        result = subprocess_wrapper.run_as_root(["/usr/sbin/diskutil", "mount", full_disk_identifier], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # FIX 1: Wenn der Mount fehlschlägt (z.B. weil Root-Rechte verweigert wurden)
        if result.returncode != 0:
            logging.error("Mount-Vorgang fehlgeschlagen! Keine ausreichenden Rechte oder Partition gesperrt.")
            logging.error("Failed to mount the drive due to not enought rights or locked partition.")
            subprocess_wrapper.log(result)
            return False  # Gibt False zurück. Der Aufrufer (die TUI) MUSS dies abfangen!

        # Festplatten-Infos nach erfolgreichem Mount auslesen
        partition_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", full_disk_identifier], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        parent_disk = partition_info["ParentWholeDisk"]
        drive_host_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", parent_disk], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        sd_type = drive_host_info.get("MediaName", "Disk")
        
        try:
            ssd_type = drive_host_info["SolidState"]
        except KeyError:
            ssd_type = False
            
        mount_path = Path(partition_info["MountPoint"])
        disk_type = partition_info["BusProtocol"]

        # FIX 2: Absicherung, falls diskutil Erfolg meldet, der Pfad aber trotzdem nicht existiert
        if not mount_path.exists():
            logging.error("EFI konnte nicht gemountet werden! Pfad existiert nicht.")
            logging.error("The EFI couldn't be mounted because the directory doesn't exist.")
            return False

        # Start der Dateioperationen
        try:
            # ESP-Schreiboperationen laufen unprivilegiert, wenn das Volume dem
            # aktuellen Benutzer gehört (FSKit auf macOS 15+); sonst als Root.
            if (mount_path / "EFI/OC").exists():
                logging.info("Entferne existierenden EFI/OC Ordner")
                logging.info("Removing existing EFI/OC folder")
                self._run_esp_file_op(["/bin/rm", "-rf", str(mount_path / "EFI/OC")], mount_path)

            if (mount_path / "System").exists():
                logging.info("Existierenden System Ordner wird entfernt")
                logging.info("Removing existing System folder")
                self._run_esp_file_op(["/bin/rm", "-rf", str(mount_path / "System")], mount_path)

            if (mount_path / "boot.efi").exists():
                logging.info("Existierende boot.efi wird entfernt")
                logging.info("Removing existing boot.efi")
                self._run_esp_file_op(["/bin/rm", str(mount_path / "boot.efi")], mount_path)

            logging.info("Die EFI-Volume mounten")
            logging.info("Mounting the EFI partition")
            self._run_esp_file_op(["/bin/mkdir", "-p", str(mount_path / "EFI")], mount_path)
            logging.info("Kopiere OpenCore auf das EFI-Volume")
            logging.info("Copying OpenCore to the EFI partition")
            self._run_esp_file_op(["/bin/cp", "-r", str(self.constants.opencore_release_folder / "EFI/OC"), str(mount_path / "EFI/OC")], mount_path)
            self._run_esp_file_op(["/bin/cp", "-r", str(self.constants.opencore_release_folder / "System"), str(mount_path / "System")], mount_path)

            if (self.constants.opencore_release_folder / "boot.efi").exists():
                logging.info("boot.efi wird zu die EFI-Partition kopiert")
                logging.info("Copying boot.efi to the EFI partition")
                self._run_esp_file_op(["/bin/cp", str(self.constants.opencore_release_folder / "boot.efi"), str(mount_path / "boot.efi")], mount_path)

            if self.constants.boot_efi is True:
                logging.info("Bootstrap zu BOOTx64.efi konvertieren")
                logging.info("Converting Bootstrap to BOOTx64.efi")
                if (mount_path / "EFI/BOOT").exists():
                    self._run_esp_file_op(["/bin/rm", "-rf", str(mount_path / "EFI/BOOT")], mount_path)

                self._run_esp_file_op(["/bin/mkdir", "-p", str(mount_path / "EFI/BOOT")], mount_path)
                self._run_esp_file_op(["/bin/mv", str(mount_path / "System/Library/CoreServices/boot.efi"), str(mount_path / "EFI/BOOT/BOOTx64.efi")], mount_path)
                self._run_esp_file_op(["/bin/rm", "-rf", str(mount_path / "System")], mount_path)
                
        except Exception as e:
            logging.error(f"Dateioperation während der Installation fehlgeschlagen: {e}")
            logging.error(f"File operation failed during installation: {e}")
            logging.exception("Stack Trace:") 
            logging.info("Bitte versuche es später erneut.")
            logging.info("Please try again later.")
            # FIX 3: sys.exit(3) muss VOR dem return stehen, sonst ist es "Dead Code"
            sys.exit(3)

        # Volume-Icons setzen (Fehler hier kopieren wir sicherheitshalber auch als Root, da EFI geschützt ist)
        try:
            if self._determine_sd_card(sd_type) is True:
                logging.info("SD-Karten Icon wird hinzugefügt")
                logging.info("Adding SD Card icon")
                self._run_esp_file_op(["/bin/cp", str(self.constants.icon_path_sd), str(mount_path)], mount_path)
            elif ssd_type is True:
                logging.info("SSD Icon wird hinzugefügt")
                logging.info("Adding SSD icon")
                self._run_esp_file_op(["/bin/cp", str(self.constants.icon_path_ssd), str(mount_path)], mount_path)
            elif disk_type == "USB":
                logging.info("USB-Stick Icon wird hinzugefügt")
                logging.info("Adding USB stick icon")
                self._run_esp_file_op(["/bin/cp", str(self.constants.icon_path_external), str(mount_path)], mount_path)
            else:
                logging.info("internes Festplatten Icon wird hinzugefügt")
                logging.info("Adding internal hard disk icon")
                self._run_esp_file_op(["/bin/cp", str(self.constants.icon_path_internal), str(mount_path)], mount_path)
        except Exception as icon_error:
            logging.warning(f"Icon-Kopie fehlgeschlagen (nicht kritisch): {icon_error}")
            logging.warning(f"Copying the icons failed (not critical): {icon_error}")

        # Bereinigung & Unmount
        logging.info("Installationsort wird bereinigt")
        logging.info("Cleaning up installation site")
        if not self.constants.recovery_status:
            logging.info("Werfe EFI-Partition aus (Unmount)")
            logging.info("Unmounting the EFI partition")
            # FIX 4: Auch unmount als Root ausführen, da wir es als Root gemountet haben
            subprocess_wrapper.run_as_root(["/usr/sbin/diskutil", "umount", mount_path])

        # FIX 5: Die Erfolgsmeldung wird NUR ausgegeben, wenn wir bis hierhin nicht abgebrochen haben!
        logging.info("OpenCore Transfer abgeschlossen")
        logging.info("OpenCore Transfer complete")
        return True

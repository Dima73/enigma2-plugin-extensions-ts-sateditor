from . import _
from Components.NimManager import nimmanager
from Plugins.Plugin import PluginDescriptor
from Tools.Directories import fileExists, resolveFilename, SCOPE_PLUGINS
from Screens.Console import Console
from Screens.Standby import TryQuitMainloop
from Screens.MessageBox import MessageBox
from Tools.BoundFunction import boundFunction
from Components.config import (
    config,
    ConfigSubsection,
    ConfigYesNo,
    ConfigSelection,
    configfile,
)
from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Button import Button
import os
import time
import shutil
import glob

# Save last chosen skin so it persists after restart
# ----------- Config Setup -----------
if not hasattr(config, "plugins"):
    config.plugins = ConfigSubsection()

if not hasattr(config.plugins, "DiskCpuTemp"):
    config.plugins.DiskCpuTemp = ConfigSubsection()

# Ensure toggle_key exists (Menu button only)
if not hasattr(config.plugins.DiskCpuTemp, "toggle_key"):
    config.plugins.DiskCpuTemp.toggle_key = ConfigSelection(
        choices=[("menu", "Menu Button")], default="menu"
    )
    try:
        config.plugins.DiskCpuTemp.toggle_key.save()
    except Exception as e:
        logMessage("Failed to save toggle_key: %s" % str(e))

config.plugins.DiskCpuTemp.last_skin = ConfigSelection(
    choices=[("Fhd1", "Fhd1"), ("Fhd2", "Fhd2")], default="Fhd2"
)

# ----------- Logging ----------
logfile = "/tmp/tssateditor.log"

# --------- Update Script Path --------
# Modify the path to include the full path to the file.
plugin_path = os.path.dirname(os.path.realpath(__file__))
loadScript = os.path.join(plugin_path, "update-xml-oe.sh")
chmod_done = False

# --------- Version from file ---------
version_file = os.path.join(plugin_path, "version.txt")
try:
    with open(version_file, "r") as f:
        plugin_version = f.read().strip()
except Exception:
    plugin_version = "Unknown"

# ----------- File Change Tracker -----------
files_changed = set()


def logMessage(msg):
    """Log messages with timestamp to /tmp/tssateditor.log"""
    try:
        with open(logfile, "a") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception as e:
        print("Failed to write log: %s" % str(e))


def ensureScriptExecutable():
    """Ensure the update script is executable, only once."""
    global chmod_done, loadScript
    if not chmod_done:
        try:
            os.chmod(loadScript, 0o755)
            logMessage("Set execute permission on %s" % loadScript)
            chmod_done = True
        except Exception as e:
            logMessage("Failed to set execute permission: %s" % str(e))


# ----------- Config Setup -----------
if not hasattr(config.misc, "tssateditorT2MI"):
    config.misc.tssateditor = ConfigSubsection()
    config.misc.tssateditorT2MI = ConfigYesNo(default=False)


# ----------- Safe XML File Copy -----------
def copyXmlFiles(src, filename, session):
    """Copy XML files safely to /etc/tuxbox with backup"""
    try:
        dst = "/etc/tuxbox/" + filename
        dst_bak = dst + ".bak"

        # Remove old backup if exists
        if fileExists(dst_bak):
            try:
                os.remove(dst_bak)
                logMessage("Removed old backup file: %s" % dst_bak)
            except Exception as e:
                logMessage("Failed to remove old backup %s: %s" % (dst_bak, str(e)))

        # Rename current file to backup if exists
        if fileExists(dst):
            try:
                os.rename(dst, dst_bak)
                logMessage("Renamed %s to %s" % (dst, dst_bak))
            except Exception as e:
                logMessage("Failed to rename %s to %s: %s" % (dst, dst_bak, str(e)))

        # small delay to be safe
        time.sleep(1)  # one Second delay to avoid crash

        # Ensure source exists before copying
        if not fileExists(src):
            logMessage("Source file does not exist, cannot copy: %s" % src)
            return False

        shutil.copy2(src, dst)
        logMessage("Successfully copied %s to %s" % (src, dst))
        return True
    except Exception as e:
        # dst may not be defined in some exception flows; guard message
        try:
            logMessage("Error copying %s to %s: %s" % (src, dst, str(e)))
        except Exception:
            logMessage("Error copying %s: %s" % (src, str(e)))
        return False


def cleanBackupFiles():
    """Remove old backup files matching known patterns"""
    try:
        for pattern in [
            "/etc/tuxbox/satellites.xml.backup.*",
            "/etc/tuxbox/terrestrial.xml.backup.*",
            "/etc/tuxbox/cables.xml.backup.*",
            "/etc/enigma2/satellites.xml.backup.*",
            "/etc/enigma2/terrestrial.xml.backup.*",
            "/etc/enigma2/cables.xml.backup.*",
        ]:
            for backup_file in glob.glob(pattern):
                try:
                    os.remove(backup_file)
                    logMessage("Removed backup file: %s" % backup_file)
                except Exception as e:
                    logMessage(
                        "Failed to remove backup file %s: %s" % (backup_file, str(e))
                    )
        return True
    except Exception as e:
        logMessage("Error cleaning backup files: %s" % str(e))
        return False


# ----------- General Update Function -----------
def updateXml(session, xml_type, filename, cmd_suffix):
    """General function to update XML files using the script"""
    global loadScript
    logMessage("update %s called" % xml_type)
    ensureScriptExecutable()

    # Add filename to files_changed so we will copy it after download
    try:
        files_changed.add(filename)
        logMessage("Marked %s for post-download copy" % filename)
    except Exception as e:
        logMessage("Failed to mark %s in files_changed: %s" % (filename, str(e)))

    # Check for update file
    if not fileExists(loadScript):
        logMessage("Error: Update script not found at %s" % loadScript)
        # Trying to find the file in alternate paths
        alternative_paths = [
            "/usr/lib/enigma2/python/Plugins/SystemPlugins/TSsatEditor/update-xml-oe.sh",
            "/tmp/update-xml-oe.sh",
            "/etc/enigma2/update-xml-oe.sh",
        ]

        for alt_path in alternative_paths:
            if fileExists(alt_path):
                loadScript = alt_path
                logMessage("Found update script at alternative path: %s" % alt_path)
                break

        # If the file is not found in any of the alternative paths
        if not fileExists(loadScript):
            session.open(
                MessageBox,
                "Update script not found!\n\nPlease check if the file exists:\n- %s\n- /usr/lib/enigma2/python/Plugins/SystemPlugins/TSsatEditor/\n- /tmp/\n- /etc/enigma2/"
                % plugin_path,
                MessageBox.TYPE_ERROR,
            )
            return

    cmd = "%s %s" % (loadScript, cmd_suffix)
    text = "Create user '/etc/enigma2/%s'" % filename
    session.openWithCallback(boundFunction(restartGui, session), Console, text, [cmd])


# ----------- Main Editor Screen -----------
class TSSatEditorScreen(Screen):

    # Auto choose skin based on resolution
    def _detect_and_set_skin(self):
        try:
            w = self.session.desktop.size().width()
            h = self.session.desktop.size().height()
            if hasattr(config.plugins.DiskCpuTemp, "last_skin"):
                saved_skin = config.plugins.DiskCpuTemp.last_skin.value
            else:
                saved_skin = None
            if saved_skin in ["Fhd1", "Fhd2"]:
                skin_to_use = saved_skin
            else:
                # Auto-detect
                skin_to_use = "Fhd1" if w < 1920 else "Fhd2"
                config.plugins.DiskCpuTemp.last_skin.value = skin_to_use
                config.plugins.DiskCpuTemp.last_skin.save()
                configfile.save()
            self.skin = (
                self._skin_fhd1() if skin_to_use == "Fhd1" else self._skin_fhd2()
            )
            logMessage("Skin applied: %s" % skin_to_use)
        except Exception as e:
            logMessage("Skin detection failed: %s" % str(e))
            self.skin = self._skin_fhd2()

    def _skin_fhd1(self):
        # Full screen FHD1 (1280x900) skin
        return """
    <screen name="TSSatEditorScreen" position="center,center" size="900,700" title=" " flags="wfNoBorder">

        <eLabel position="0,0" size="1280,60" backgroundColor="#333333" zPosition="-1" />
        
        <widget name="header_left" position="10,5" size="450,30" font="Regular;26"
            halign="left" valign="center" foregroundColor="#FFFF00" />
        <widget name="header_right" position="460,5" size="430,30" font="Regular;26"
            halign="right" valign="center" foregroundColor="#FFFF00" />

        <widget name="btn_red" position="10,60" size="176,40" font="Regular;22"
            halign="center" valign="center" backgroundColor="red" foregroundColor="white" />
        <widget name="btn_green" position="186,60" size="176,40" font="Regular;22"
            halign="center" valign="center" backgroundColor="green" foregroundColor="black" />
        <widget name="btn_yellow" position="362,60" size="176,40" font="Regular;22"
            halign="center" valign="center" backgroundColor="yellow" foregroundColor="black" />
        <widget name="btn_blue" position="538,60" size="176,40" font="Regular;22"
            halign="center" valign="center" backgroundColor="blue" foregroundColor="white" />
        <widget name="btn_menu" position="714,60" size="176,40" font="Regular;22"
            halign="center" valign="center" backgroundColor="#8A2BE2" foregroundColor="white" />

        <ePixmap position="20,120" size="880,450" pixmap="skin_default/menu_back.png" zPosition="-1" />
        <widget name="menu" position="20,120" size="880,450" font="Regular;30"
            itemHeight="50" scrollbarMode="showOnDemand"
            backgroundColor="#303030" foregroundColor="white" />

        <widget name="info_label" position="0,650" size="900,40" font="Regular;26"
            halign="center" valign="center" foregroundColor="#00FF00" />

        <eLabel position="0,600" size="900,30" backgroundColor="#333333" zPosition="-1" />
        <widget name="footer" position="0,600" size="900,40" font="Regular;26"
            halign="center" valign="center" foregroundColor="#FFFF00" />
    </screen>
    """

    def _skin_fhd2(self):
        # Full screen FHD2 (1920x1080) skin
        return """
    <screen name="TSSatEditorScreen" position="center,center" size="1920,1080" title=" " flags="wfNoBorder">

        <eLabel position="0,0" size="1920,60" backgroundColor="#3333FF" zPosition="-1" />
        
        <widget name="header_left" position="20,15" size="960,60" font="Regular;36"
            halign="left" valign="center" foregroundColor="#FFFF00" />
        <widget name="header_right" position="980,15" size="920,60" font="Regular;36"
            halign="right" valign="center" foregroundColor="#FFFF00" />

        <widget name="btn_red" position="60,80" size="300,60" font="Regular;32"
            halign="center" valign="center" backgroundColor="red" foregroundColor="white" />
        <widget name="btn_green" position="380,80" size="300,60" font="Regular;32"
            halign="center" valign="center" backgroundColor="green" foregroundColor="black" />
        <widget name="btn_yellow" position="700,80" size="300,60" font="Regular;32"
            halign="center" valign="center" backgroundColor="yellow" foregroundColor="black" />
        <widget name="btn_blue" position="1020,80" size="300,60" font="Regular;32"
            halign="center" valign="center" backgroundColor="blue" foregroundColor="white" />
        <widget name="btn_menu" position="1340,80" size="300,60" font="Regular;32"
            halign="center" valign="center" backgroundColor="#8A2BE2" foregroundColor="white" />

        <ePixmap position="60,40" size="1800,800" pixmap="skin_default/menu_back.png" zPosition="-1" />
        <widget name="menu" position="60,170" size="1800,800" font="Regular;36"
            itemHeight="60" scrollbarMode="showOnDemand"
            backgroundColor="#303030" foregroundColor="white" />

        <widget name="info_label" position="0,1020" size="1920,50" font="Regular;30"
            halign="center" valign="center" foregroundColor="#00FF00" />

        <eLabel position="0,970" size="1920,50" backgroundColor="#333333" zPosition="-1" />
        <widget name="footer" position="0,970" size="1920,50" font="Regular;30"
            halign="center" valign="center" foregroundColor="#FFFF00" />
    </screen>
    """

    # ---------- Skin Change ----------

    def change_skin(self):
        # Ask user Yes/No before changing skin
        def yesnoCallback(result):
            if result is True:
                try:
                    current = config.plugins.DiskCpuTemp.last_skin.value
                except:
                    current = "Fhd2"
                new_skin = "Fhd1" if current == "Fhd2" else "Fhd2"
                config.plugins.DiskCpuTemp.last_skin.value = new_skin
                config.plugins.DiskCpuTemp.last_skin.save()
                configfile.save()
                logMessage("Skin changed to %s - saved" % new_skin)
                self.session.open(TryQuitMainloop, 3)
            else:
                logMessage("Skin change cancelled by user")

        self.session.openWithCallback(
            yesnoCallback,
            MessageBox,
            "Do you really want to change the skin?",
            MessageBox.TYPE_YESNO,
        )

    # -------- Init ----------
    def __init__(self, session, menu, callback):
        logMessage("Initializing TSSatEditorScreen")
        Screen.__init__(self, session)

        # Choose skin based on saved preference
        try:
            skin_choice = config.plugins.DiskCpuTemp.last_skin.value
        except Exception:
            skin_choice = "Fhd2"

        if skin_choice == "Fhd1":
            skin = self._skin_fhd1()
        else:
            skin = self._skin_fhd2()

        self.skin = skin

        self["header_left"] = Label("TS Satellite Editor Modified By iet5")
        self["header_right"] = Label("VER %s" % plugin_version)

        # Buttons
        self["btn_red"] = Button(_("Exit"))
        self["btn_green"] = Button(_("Update Satellites"))
        self["btn_yellow"] = Button(_("Update Terrestrial"))
        self["btn_blue"] = Button(_("Update Cables"))
        self["btn_menu"] = Button(_("Change Skin"))

        # Menu
        self.menu = menu
        self["menu"] = MenuList([str(m[0]) for m in menu])

        # New info label above footer
        self["info_label"] = Label(_("Use Menu button to toggle resolution"))

        # Footer Label
        self["footer"] = Label(
            _("Developed by mfaraj57 ** Modified for Py3 by ** iet5")
        )

        # Callback and closed state
        self.callback = callback
        self._closedAlready = False

        # Actions Mapping
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "MenuActions"],
            {
                "ok": self.okClicked,
                "cancel": self.cancel,
                "red": self.cancel,
                "green": lambda: updateXml(
                    session, "satellites", "satellites.xml", "dvbs"
                ),
                "yellow": lambda: updateXml(
                    session, "terrestrial", "terrestrial.xml", "dvbt"
                ),
                "blue": lambda: updateXml(session, "cables", "cables.xml", "dvbc"),
                "menu": self.change_skin,
            },
            -1,
        )

    # ------------- Safe Close --------------
    def safeClose(self, result=None):
        """Close the screen safely to avoid multiple closures"""
        if self._closedAlready:
            logMessage("safeClose called but already closed")
            return
        self._closedAlready = True
        logMessage("safeClose executing, result: %s" % str(result))
        self.close(result)
        logMessage("Screen closed successfully.")

    # ------------- Menu OK Click ---------------
    def okClicked(self):
        """Handle OK button on menu"""
        cur = self["menu"].getCurrent()
        logMessage("okClicked called, current: %s" % cur)
        if cur:
            for m in self.menu:
                if m[0] == cur:
                    self.safeClose(m)
                    return
        self.safeClose(None)

    # ----------- Cancel / Exit ---------------
    def cancel(self):
        """Handle cancel, ESC or Red button"""
        logMessage("Cancel triggered (red button / ESC).")
        self.safeClose(None)


# ----------- GUI Restart -----------
def restartGui(session=None):
    logMessage("restartGui called")
    if files_changed and session:
        # Copy only the files that were actually changed
        for filename in list(files_changed):
            src = "/etc/enigma2/%s" % filename
            dst = "/etc/tuxbox/%s" % filename  # target
            try:
                if fileExists(src):
                    success = copyXmlFiles(src, filename, session)
                    if success:
                        # remove from set to avoid duplicate copying
                        files_changed.discard(filename)
                else:
                    logMessage("Source file not found for copy: %s" % src)
            except Exception as e:
                logMessage("Exception during copying %s: %s" % (filename, str(e)))

        # cleanup old backup files for only changed files
        for filename in list(files_changed):
            try:
                bak_pattern = "/etc/tuxbox/%s.bak*" % filename
                for backup_file in glob.glob(bak_pattern):
                    try:
                        os.remove(backup_file)
                        logMessage("Removed backup file: %s" % backup_file)
                    except Exception as e:
                        logMessage(
                            "Failed to remove backup file %s: %s"
                            % (backup_file, str(e))
                        )
            except Exception as e:
                logMessage(
                    "Error cleaning backup files for %s: %s" % (filename, str(e))
                )

        # wait a bit to ensure file copying is done
        time.sleep(1)

        # ask user if they want to restart GUI
        try:
            session.openWithCallback(
                boundFunction(restartGuiNow, session),
                MessageBox,
                "Files copied to /etc/tuxbox.\nDo you want to restart the GUI now?",
                MessageBox.TYPE_YESNO,
            )
        except Exception as e:
            logMessage("Failed to open restart confirmation MessageBox: %s" % str(e))


def restartGuiNow(session, answer):
    """Perform the actual GUI restart based on user answer"""
    logMessage("restartGuiNow called, answer: %s" % str(answer))
    if answer and session:
        logMessage("User confirmed restart. Restarting GUI now...")
        try:
            session.open(TryQuitMainloop, 3)
        except Exception as e:
            logMessage("Failed to call TryQuitMainloop: %s" % str(e))
    else:
        logMessage("Restart cancelled by user or no session provided.")


# ----------- Main Function -----------
def SatellitesEditorMain(session, **kwargs):
    """Main menu function to display options and handle user choice"""
    menu = []
    logMessage("SatellitesEditorMain called")
    text = _("Select action:")

    # DVB-S Options
    if fileExists("/etc/enigma2/satellites.xml"):
        menu.append((_("Open user '/etc/enigma2/satellites.xml'"), "openedit"))
        menu.append((_("Disable user '/etc/enigma2/satellites.xml'"), "disable"))
        menu.append((_("Remove user '/etc/enigma2/satellites.xml'"), "remove"))
    else:
        if not fileExists("/etc/enigma2/satellites.xml.disabled"):
            menu.append((_("Create user '/etc/enigma2/satellites.xml'"), "create"))
            menu.append(
                (
                    _("Create user '/etc/enigma2/satellites.xml' (use default)"),
                    "createdefault",
                )
            )
        else:
            menu.append((_("Enable user '/etc/enigma2/satellites.xml'"), "enable"))

    menu.append(
        (
            (
                _("Use TSID/ONID")
                if config.misc.tssateditorT2MI.value
                else _("Use T2MI PLP")
            ),
            "t2mi",
        )
    )
    # DVB-T Options
    if nimmanager.hasNimType("DVB-T"):
        menu.append(
            (
                (
                    _("Remove user '/etc/enigma2/terrestrial.xml'")
                    if fileExists("/etc/enigma2/terrestrial.xml")
                    else _("Create user '/etc/enigma2/terrestrial.xml'")
                ),
                "dvbt",
            )
        )
    # DVB-C Options
    if nimmanager.hasNimType("DVB-C"):
        menu.append(
            (
                (
                    _("Remove user '/etc/enigma2/cables.xml'")
                    if fileExists("/etc/enigma2/cables.xml")
                    else _("Create user '/etc/enigma2/cables.xml'")
                ),
                "dvbc",
            )
        )

    def boxAction(choice):
        logMessage("boxAction called with choice: %s" % str(choice))
        if choice is None:
            logMessage("User exited without selection")
            return

        # DVB-S
        if choice[1] == "openedit":
            logMessage("Opening satellites.xml in editor")
            from .satedit import SatellitesEditor

            files_changed.clear()
            files_changed.add("satellites.xml")
            session.openWithCallback(
                boundFunction(restartGui, session), SatellitesEditor
            )
        elif choice[1] == "disable":
            if fileExists("/etc/enigma2/satellites.xml"):
                os.rename(
                    "/etc/enigma2/satellites.xml",
                    "/etc/enigma2/satellites.xml.disabled",
                )
        elif choice[1] == "remove":

            def removeFile(answer, filepath="/etc/enigma2/satellites.xml"):
                if answer and fileExists(filepath):
                    try:
                        os.remove(filepath)
                        logMessage("%s removed successfully" % filepath)
                    except Exception as e:
                        logMessage("Failed to remove %s: %s" % (filepath, str(e)))

            session.openWithCallback(
                removeFile,
                MessageBox,
                _("Do you really want to remove satellites.xml?"),
                MessageBox.TYPE_YESNO,
                default=False,
            )
        elif choice[1] == "enable":
            if fileExists("/etc/enigma2/satellites.xml.disabled"):
                os.rename(
                    "/etc/enigma2/satellites.xml.disabled",
                    "/etc/enigma2/satellites.xml",
                )
        elif choice[1] == "createdefault":
            if fileExists("/etc/tuxbox/satellites.xml"):
                try:
                    shutil.copy2(
                        "/etc/tuxbox/satellites.xml", "/etc/enigma2/satellites.xml"
                    )
                    logMessage(
                        "Copied default /etc/tuxbox/satellites.xml to /etc/enigma2/satellites.xml"
                    )
                except Exception as e:
                    logMessage("Failed to copy default satellites.xml: %s" % str(e))
        elif choice[1] == "create":
            updateXml(session, "satellites", "satellites.xml", "dvbs")
        elif choice[1] in ["dvbt", "dvbc"]:
            xml_map = {
                "dvbt": ("terrestrial.xml", "dvbt"),
                "dvbc": ("cables.xml", "dvbc"),
            }
            filename, cmd_suffix = xml_map[choice[1]]
            action = (
                _("Remove user '/etc/enigma2/%s'" % filename)
                if fileExists("/etc/enigma2/%s" % filename)
                else _("Create user '/etc/enigma2/%s'" % filename)
            )
            if "Remove" in action:

                def removeXml(answer, filepath="/etc/enigma2/%s" % filename):
                    if answer and fileExists(filepath):
                        try:
                            os.remove(filepath)
                            logMessage("%s removed successfully" % filepath)
                        except Exception as e:
                            logMessage("Failed to remove %s: %s" % (filepath, str(e)))

                session.openWithCallback(
                    removeXml,
                    MessageBox,
                    _("Do you really want to remove %s?" % filename),
                    MessageBox.TYPE_YESNO,
                    default=False,
                )
            else:
                updateXml(session, filename.split(".")[0], filename, cmd_suffix)
        elif choice[1] == "t2mi":
            config.misc.tssateditorT2MI.value = not config.misc.tssateditorT2MI.value
            config.misc.tssateditorT2MI.save()
            session.openWithCallback(boxAction, TSSatEditorScreen, menu, boxAction)

    # Open screen
    session.openWithCallback(boxAction, TSSatEditorScreen, menu, boxAction)


# ----------- Plugin Descriptor -----------
def SatellitesEditorStart(menuid, **kwargs):
    if menuid == "scan":
        return [(_("TS-Satellites Editor"), SatellitesEditorMain, "sat_editor", None)]
    return []


def Plugins(**kwargs):
    if nimmanager.hasNimType("DVB-S"):
        return [
            PluginDescriptor(
                name=_("TS-Satellites Editor"),
                description=_("User satellites.xml"),
                where=PluginDescriptor.WHERE_MENU,
                fnc=SatellitesEditorStart,
            )
        ]
    return []

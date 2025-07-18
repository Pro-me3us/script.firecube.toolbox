# File: gui_main_menu.py
import xbmcgui
import xbmc
import os
import subprocess
import xbmcaddon

from resources.lib import (
    bt_sync,
    boot_order,
    boot_trigger_time,
    change_wifi_mac,
    suspend_service,
    cpu_overclock,
    cube_update,
    ir_trigger,
    button_trigger,
    dv_download,
    commandcraft
)

ADDON_PATH = xbmcaddon.Addon().getAddonInfo('path')
UPDATE_GZ = os.path.join(ADDON_PATH, "resources", "update", "misc.img.gz")

MENU_ITEMS = [
    ("Bluetooth sync FireOS Fire remotes with CoreELEC", "bt_sync"),
    ("Change WiFi MAC address", "wifi_mac"),
    ("Enable suspend & IR triggered wakeup", "suspend"),
    ("Copy CoreELEC installation from USB to eMMC", "move_emmc"),
    ("Install CommandCraft app to FireOS", "commandcraft"),
    ("Set boot order", "boot_order"),
    ("Set boot trigger delay (green LED)", "boot_delay"),
    ("Set IR remote boot triggers", "ir_trigger"),
    ("Set Cube button boot triggers", "cube_button"),
    ("Overclock CPU (use at your own risk)", "overclock")
]

DESCRIPTIONS = {
    "cube_update": "Update to get latest features and capabilities. Changes got into effect after a reboot",
    "bt_sync": "Imports Bluetooth pairings from FireOS, allowing any Fire remotes to be Bluetooth paired in both CoreELEC and FireOS.  First pair remote in FireOS, then re-run this option to add it CoreELEC. Requires a reboot.",
    "wifi_mac": "Change WiFi MAC address, or match the MAC used in FireOS.  The same default MAC is used by CoreELEC for all Cubes.  Avoid network conflicts when using more than one Cube on the same network. Requires a reboot, and WiFi password re-entry.",
    "suspend": "Allows suspend/waking Cube in CoreELEC.  Wakeup requires IR trigger defined in remote.conf.  Use FireOS equipment control setup to program remote to function in both Bluetooth and IR.  Fire television IR profile is used by default for wakeup.",
    "move_emmc": "Copy CoreELEC from USB Stick entirely to eMMC (/flash and /storage). Copy /flash to eMMC from previous USB/hybrid install (USB stick no longer needed to boot), choose /flash only.",
    "boot_order": "Choose what OS boots by default. If no USB Stick is present, Cube automatically proceeds to eMMC OS.  Booting directly to FireOS or CoreELEC allows keeping a bootable USB stick (eg EmuELEC) attached that only boots when manually triggered.",
    "boot_delay": "During boot there's a delay marked by the green LED when the Cube listens for an IR or Cube button press to override what OS to boot.  The default delay is 1 second.",
    "ir_trigger": "Configure what IR codes trigger what boot option.  Each boot option can be triggered by two different IR codes, to use more than one remote model.  Use the IR code detect option if unsure of the code, only works with the NEC protocol.",
    "cube_button": "Configure the Cube Volume Up/Down and Action buttons to trigger boot target during green LED.  Volume Up (fastboot), Volume Down (TWRP) and Action (AML Update) buttons can also be held down before the green LED for additional options.",
    "overclock": "Overclock big/little cores up to 2.4GHz/2.0GHz for a 9-10% performance boost.  The ondemand option keeps the stock CPU frequencies, only ramping up overclocked frequencies under high CPU load.  Use cautiously. Reboot required.",
    "enable_dv": "Add Dolby Vision module to Cube (/storage/dovi.ko) to enable DV playback.  Requires a reboot.",
    "commandcraft": "CommandCraft is a lightweight FireOS/Android app (60KB) that makes it easy to select any of the Cube's rebooting options (FireOS, TWRP, CE, Fastboot, USB Boot, AML update, power off, soft reboot).  Edit or add your own ADB shell buttons."
}

class MainMenu(xbmcgui.WindowXMLDialog):
    def onInit(self):
        self.list = self.getControl(1000)
        self.desc = self.getControl(1001)
        self.load_menu()
        self.update_description()

        skin_name = xbmc.getSkinDir()
        xbmc.log(f"Current skin: {skin_name}", xbmc.LOGINFO)
        xbmc.executebuiltin(f"Skin.SetString(CurrentSkin, {skin_name})")
        supported_skins = ["skin.estuary", "arctic.zephyr"]
        skin_unsupported = not any(supported_skin in skin_name for supported_skin in supported_skins)
        if skin_unsupported:
            xbmc.executebuiltin('Skin.SetString(SkinUnsupported,true)')
        else:
            xbmc.executebuiltin('Skin.Reset(SkinUnsupported)')

        xbmc.sleep(200)
        xbmc.executebuiltin("SetFocus(1000)")

    def load_menu(self):
        items = MENU_ITEMS.copy()

        if os.path.exists(UPDATE_GZ):
            update_ts = cube_update._read_gz_misc_timestamp(UPDATE_GZ)
            current_ts = cube_update._read_misc_timestamp("/dev/misc")
            if update_ts and current_ts and update_ts > current_ts:
                items.insert(0, ("Cube update for CE available", "cube_update"))

        if not any(os.path.exists(p) for p in ["/flash/dovi.ko", "/storage/dovi.ko", "/storage/.config/dovi.ko"]):
            insert_index = 1 if items and items[0][1] == "cube_update" else 0
            items.insert(insert_index, ("Enable Dolby Vision", "enable_dv"))

        self.menu_items = items
        for label, _ in items:
            self.list.addItem(xbmcgui.ListItem(label))

        xbmc.log(f"[FireCubeToolbox] {len(items)} menu items loaded", xbmc.LOGINFO)

    def update_description(self):
        selected_pos = self.list.getSelectedPosition()
        if 0 <= selected_pos < len(self.menu_items):
            _, action = self.menu_items[selected_pos]
            description = DESCRIPTIONS.get(action, "")
            self.desc.setText(description)

    def onAction(self, action):
        action_id = action.getId()
        if action_id in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_PAGE_UP, xbmcgui.ACTION_PAGE_DOWN):
            self.update_description()
        elif action_id in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.close()
        super(MainMenu, self).onAction(action)

    def onClick(self, controlId):
        if controlId == 1000:
            index = self.list.getSelectedPosition()
            if index < 0 or index >= len(self.menu_items):
                return
            _, action = self.menu_items[index]
            self.run_action(action)
        elif controlId == 1500:
            self.close()

    def run_action(self, action):
        if action == "cube_update":
            if cube_update.apply_update():
                self.list.reset()
                self.load_menu()
                self.update_description()
        elif action == "bt_sync":
            bt_sync.sync_firetv_remote()
        elif action == "wifi_mac":
            change_wifi_mac.show_wifi_mac_menu()
        elif action == "suspend":
            suspend_service.show_suspend_menu()
        elif action == "move_emmc":
            move_opts = ["Move /flash + /storage to eMMC (full migration)", "/flash only (hybrid USB/eMMC install)"]
            sel = xbmcgui.Dialog().select("Move to eMMC", move_opts)
            if sel == 0:
                self.run_move_to_emmc("full")
            elif sel == 1:
                self.run_move_to_emmc("flash")
        elif action == "boot_order":
            boot_order.show_boot_order_menu()
        elif action == "boot_delay":
            boot_trigger_time.set_boot_led_delay()
        elif action == "ir_trigger":
            ir_trigger.get_ir_boot_triggers()
        elif action == "cube_button":
            button_trigger.get_cube_button_triggers()
        elif action == "overclock":
            cpu_overclock.show_overclock_menu()
        elif action == "enable_dv":
            if dv_download.enable_dolby_vision():
                self.list.reset()
                self.load_menu()
                self.update_description()
        elif action == "commandcraft":
            commandcraft.run()

    def run_move_to_emmc(self, option):
        if os.path.exists(UPDATE_GZ):
            update_ts = cube_update._read_gz_misc_timestamp(UPDATE_GZ)
            current_ts = cube_update._read_misc_timestamp("/dev/misc")
            if update_ts and current_ts and update_ts > current_ts:
                xbmcgui.Dialog().ok("Cube Update Required", "Please apply the available Cube Update before eMMC migration")
                return

        script_path = "/storage/.kodi/addons/script.firecube.toolbox/resources/bin/emmc_install.sh"
        arg = "--flash-only" if option == "flash" else "--full"
        xbmcgui.Dialog().ok("eMMC Migration", "Stop Kodi to move files to eMMC.")
        subprocess.call(["systemd-run", "--no-block", "/bin/sh", script_path, arg])
        xbmc.executebuiltin("Dialog.Close(all,true)")


import logging
import subprocess
import threading
import os
import time
import re
import pydbus

from gi.repository import GLib

discovery_time = 10
mainloop = GLib.MainLoop()

logger = logging.getLogger(__name__)

bus = pydbus.SystemBus()

bluez_service = 'org.bluez'
mngr = bus.get(bluez_service, '/')

adapter_path = '/org/bluez/hci0'
adapter = bus.get(bluez_service, adapter_path) 
bluez = bus.get("org.freedesktop.DBus", "/org/bluez")


class BluetoothDbusController():
    def __init__(self, core, config):
        self.config = config
        self.core = core
        self.devices = []
        self.wait_time = 0
        self.connection_semaphore = threading.Semaphore(4)


    def address_path(self, address):
        return f"{adapter_path}/dev_{address.replace(':', '_')}"


    def scan_devices(self):
        """Scan for trusted Bluetooth devices and return a list of device Name and MAC addresses."""
        logger.info("Scanning for available Bluetooth devices...")
        def end_discovery():
            """Handler for end of discovery"""
            mainloop.quit()
            adapter.StopDiscovery()
        try:
            adapter.StartDiscovery()
            GLib.timeout_add_seconds(discovery_time, end_discovery)
            mainloop.run()

            mng_objs = mngr.GetManagedObjects()       
            devices = []
            for path in mng_objs:
                device = mng_objs[path].get('org.bluez.Device1')
                if device and device.get('Name'):
                    devices.append({
                        "name": device.get("Name"),
                        "address": device.get("Address"),
                        "alias": device.get("Alias"),
                        "icon": device.get("Icon"),
                        "path": path
                    })
            self.devices = devices        
            return devices
        except Exception:
            raise RuntimeError(f"Failed to scan for bluetooth devices")


    def get_devices(self):
        """Gets the list of devices cached from last scan"""
        return self.devices


    def adapter_power(self, state):
        try:
            value = GLib.Variant("b", state)
            adapter.Set("org.bluez.Adapter1", "Powered", value)
            return True
        except Exception:
            raise RuntimeError(f"Failed to change adapter power state")


    def get_device_info(self, address):
        """Gets currently connected device information"""
        try:
            device = bus.get(bluez_service, self.address_path(address))
            device_info = [{
                            "adapter": device.Adapter,
                            "alias": device.Alias,
                            "address": device.Address,
                            "icon": device.Icon,
                            "path": self.address_path(address),
                            "paired": device.Paired,
                            "trusted": device.Trusted,
                            "class": device.Class,
                            "bonded":device.Bonded,
                        }]
            return device_info
        except Exception:
            raise RuntimeError(f"Failed to device info for {address}")
        

    def get_device_player(self, address):
        try:
            device = bus.get(bluez_service, f"{self.address_path(address)}/player0")
            device_player = [{
                            "status": device.Status,
                            "device": device.Device,
                            "name": device.Name,
                            "track": device.Track,
                            "type": device.Type,
                            "position": device.Position,
                        }]
            return device_player
        except Exception:
            raise RuntimeError(f"Failed to fetch player for {address}")

        
    def player_stop(self, address):
        device = bus.get(bluez_service, self.address_path(address))
        device.Stop()
        return True
    

    def player_play(self, address):
        device = bus.get(bluez_service, self.address_path(address))
        device.Play()
        return True


    def player_pause(self, address):
        device = bus.get(bluez_service, self.address_path(address))
        device.Pause()
        return True


    def player_prev(self, address):
        device = bus.get(bluez_service, self.address_path(address))
        device.Previous()
        return True
    

    def player_next(self, address):
        device = bus.get(bluez_service, self.address_path(address))
        device.Next()
        return True


    def trust_devices(self, address):
        try:
            """Trusts a bluetooth devices with mac address"""
            logger.debug(f"Attempting to Trust to {address}...")
            device = bus.get(bluez_service, self.address_path(address))
            value = GLib.Variant("b", True)
            device.Set("org.bluez.Device1","Trusted",value)
            return True
        except Exception:
                raise RuntimeError(f"Failed to trust device {address}")
        

    def connect_device(self, address):
        try:
            """Connects to bluetooth device with address."""
            logger.debug(f"Attempting to connect to {address}...")
            device = bus.get(bluez_service, self.address_path(address))
            device.Connect()
            return True
        except Exception:
            raise RuntimeError(f"Failed to connect device {address}")


    def disconnect_device(self, address):
        try:
            """Disconnects a bluetooth device"""
            logger.debug(f"Attempting to disconnect from {address}")
            device = bus.get(bluez_service, self.address_path(address))
            device.Disconnect()
            return True
        except Exception:
            raise RuntimeError(f"Failed to disconnect device {address}")
        

    def remove_device(self, address):
        try:
            """Removes a bluetooth devices."""
            logger.debug(f"Removing device {address}")
            adapter.RemoveDevice(self.address_path(address))
            return True
        except Exception:
            raise RuntimeError(f"Failed to remove device {address}")
        
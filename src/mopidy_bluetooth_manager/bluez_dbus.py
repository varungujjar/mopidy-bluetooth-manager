
import logging
import pydbus
from mopidy.core.listener import CoreListener

from gi.repository import GLib, GObject

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


    def on_properties_changed(self, *args):
        interface = args[1]
        params = args[4]

        if adapter_path in interface:
            properties = params[1]

            if "State" in properties:
                CoreListener.send("playback_state_changed", state=properties["State"])
           
            if "Status" in properties:
                CoreListener.send("playback_status_changed", status=properties["Status"])

            if "Connected" in properties:
                value = properties.get("Connected")
                if value:
                    CoreListener.send("network_status_changed", connected=value, device=self.get_device(interface))
                    CoreListener.send("input_source_changed", source='bluetooth')
                else:
                    CoreListener.send("network_status_changed", connected=value, device=self.get_device(interface))
               
            if "Track" in properties:
                CoreListener.send("tracklist_changed", track=properties["Track"])

            if "Volume" in properties:
                CoreListener.send("volume_changed", volume=properties["Volume"])

            if "Discovering" in properties:
                CoreListener.send("network_state_changed", discovering=properties["Discovering"])
           


    def start_dbus_listener(self):
        bus.subscribe(
            iface="org.freedesktop.DBus.Properties",
            signal="PropertiesChanged",
            signal_fired=self.on_properties_changed
        )


    def adapter_power(self, state):
        """Bluetooth power switch"""
        try:
            value = GLib.Variant("b", state)
            adapter.Set("org.bluez.Adapter1", "Powered", value)
            return True
        except Exception:
            raise RuntimeError(f"Failed to change adapter power state")


    def discover_devices(self):
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
            logger.info(f"Found ({len(devices)}) Bluetooth devices.")
            return devices
        except Exception:
            raise RuntimeError(f"Failed to scan for bluetooth devices")


    def get_devices(self):
        """Gets the list of devices cached from last scan"""
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
                    "path": path,
                    "connected":device.get("Connected")
                })
        return devices


    def get_device(self, device_path = None):
        """Gets device information by path or 
           currently connected device.
        """
        if device_path is not None:
            try:
                device = bus.get(bluez_service, device_path)
                return {
                            "adapter": device.Adapter,
                            "alias": device.Alias,
                            "address": device.Address,
                            "icon": device.Icon,
                            "path": device_path,
                            "paired": device.Paired,
                            "trusted": device.Trusted,
                            "class": device.Class,
                            "bonded":device.Bonded,
                        }
            except Exception:
                raise RuntimeError(f"Failed to device info for {device_path}")
        else:
            mng_objs = mngr.GetManagedObjects()      
            for path in mng_objs:
                device = mng_objs[path].get('org.bluez.Device1')
                if device and device.get('Connected'):
                     return {
                                "name": device.get("Name"),
                                "address": device.get("Address"),
                                "alias": device.get("Alias"),
                                "icon": device.get("Icon"),
                                "path": path,
                                "connected":device.get("Connected")
                            }


    def get_player(self, device_path):
        """Gets device media player information"""
        try:
            device = bus.get(bluez_service, f"{device_path}/player0")
            device_player = [{
                            "status": device.get("Status"),
                            "device": device.get("Device"),
                            "name": device.get("Name"),
                            "track": device.get("Track"),
                            "type": device.get("Type"),
                            "position": device.get("Position"),
                        }]
            return device_player
        except Exception:
            return "Not supported on this device"

    def device_trust(self, device_path):
        """Trusts a bluetooth devices with mac address"""
        try:
            logger.debug(f"Attempting to Trust to {device_path}...")
            device = bus.get(bluez_service, device_path)
            value = GLib.Variant("b", True)
            device.Set("org.bluez.Device1","Trusted",value)
            return True
        except Exception:
                raise RuntimeError(f"Failed to trust device {device_path}")
        

    def device_connect(self, device_path):
        try:
            """Connects to bluetooth device with address."""
            logger.debug(f"Attempting to connect to {device_path}...")
            device = bus.get(bluez_service, device_path)
            device.Connect()
            return True
        except Exception:
            raise RuntimeError(f"Failed to connect device {device_path}")


    def device_disconnect(self, device_path):
        try:
            """Disconnects a bluetooth device"""
            logger.debug(f"Attempting to disconnect from {device_path}")
            device = bus.get(bluez_service, device_path)
            device.Disconnect()
            return True
        except Exception:
            raise RuntimeError(f"Failed to disconnect device {device_path}")
        

    def device_remove(self, device_path):
        try:
            """Removes a bluetooth devices."""
            logger.debug(f"Removing device {device_path}")
            adapter.RemoveDevice(device_path)
            return True
        except Exception:
            raise RuntimeError(f"Failed to remove device {device_path}")
        

    def player_stop(self, device_path):
        """Bluetooth device player Stop command"""
        device = bus.get(bluez_service, device_path)
        device.Stop()
        return True
    

    def player_play(self, device_path):
        """Bluetooth device player Play command"""
        device = bus.get(bluez_service, device_path)
        device.Play()
        return True


    def player_pause(self, device_path):
        """Bluetooth device player Pause command"""
        device = bus.get(bluez_service, device_path)
        device.Pause()
        return True


    def player_prev(self, device_path):
        """Bluetooth device player Previous command"""
        device = bus.get(bluez_service, device_path)
        device.Previous()
        return True
    

    def player_next(self, device_path):
        """Bluetooth device player Next command"""
        device = bus.get(bluez_service, device_path)
        device.Next()
        return True


    
        
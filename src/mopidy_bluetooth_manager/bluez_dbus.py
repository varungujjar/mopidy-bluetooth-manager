
import logging
import pydbus
import time
import subprocess
import re

from mopidy.core.listener import CoreListener
from mopidy.models import Album, Artist, Track, TlTrack
from mopidy.types import PlaybackState, DurationMs

from gi.repository import GLib, GObject

discovery_time = 20
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
        self.track = None
        self.track_mem = None

    def set_track(self, _track = None):
        _track_id = 1
        track = Track(
            name = _track.get("Title") if _track.get("Title") else 'Bluetooth',
            artists = frozenset([Artist(name=_track.get("Artist"))]) if _track.get("Artist") else frozenset([Artist(name="Unknown")]),
            album = Album(name=_track.get("Album")) if _track.get("Album") else None,
            track_no =  int(_track.get("TrackNumber")) if _track.get("TrackNumber") is not None else None,
            length = int(_track.get("Duration")) if _track.get("Duration") is not None else None,  
        )
        tl_track = TlTrack(_track_id, track=track)
        self.track = tl_track
        self.core.playback.set_metadata(tl_track)
        CoreListener.send("track_playback_started", tl_track=tl_track)

    def on_properties_changed(self, *args):
        interface = args[1]
        params = args[4]

        if adapter_path in interface:
            properties = params[1]

            if "State" in properties:
                CoreListener.send("options_changed", state=properties["State"])
            
            if "Status" in properties:
                # CoreListener.send("playback_status_changed", status=properties["Status"])
                if (properties["Status"] == 'playing'):
                    self.core.playback.set_state(PlaybackState.PLAYING)
                if (properties["Status"] == 'paused'):
                    self.core.playback.set_state(PlaybackState.PAUSED)

            if "Connected" in properties and not "Player" in properties:
                value = properties.get("Connected")
                self.core.playback.stop()
                if value:
                    # self.track_mem = self.core.playback.get_current_track()
                    CoreListener.send("network_status_changed", connected=value, device=self.get_device(interface))
                    CoreListener.send("options_changed", input='bluetooth')
                    self.set_track({})
                    self.handle_incoming_device_request(self.get_device(interface))
                else:
                    self.core.playback.set_state(PlaybackState.STOPPED)
                    self.core.playback.set_metadata(None)
                    CoreListener.send("track_playback_ended")
                    CoreListener.send("network_status_changed", connected=value, device=self.get_device(interface))
               
            if "Track" in properties:
                if self.track is not None:
                    CoreListener.send("track_playback_ended", tl_track=self.track)
                
                _track = properties.get("Track")
                if _track:
                    self.set_track(_track)

            if "Volume" in properties:
                CoreListener.send("volume_changed", volume=properties["Volume"])

            if "Discovering" in properties:
                CoreListener.send("network_status_changed", discovering=properties["Discovering"])

            if "Discoverable" in properties:
                CoreListener.send("network_state_changed", discover=properties["Discoverable"])


    def start_dbus_listener(self):
        bus.subscribe(
            iface="org.freedesktop.DBus.Properties",
            signal="PropertiesChanged",
            signal_fired=self.on_properties_changed
        )
        connected_device = self.get_device()
        if (connected_device):
            self.set_track({})
            CoreListener.send("options_changed", input='bluetooth')


    def adapter_power(self, state):
        """Bluetooth power switch"""
        try:
            value = GLib.Variant("b", state)
            adapter.Set("org.bluez.Adapter1", "Powered", value)
            return True
        except Exception:
            raise RuntimeError(f"Failed to change adapter power state")


    def adapter_set_name(self, name):
        """Sets Name to bluetooth device """

        try:
            logger.info(f"Starting bluetooth with name {name}")
            name_alias = GLib.Variant("s", name)
            adapter.Set("org.bluez.Adapter1","Alias", name_alias)

            return True
        except Exception:
                raise RuntimeError(f"Failed to set device name {name}")
        
    def set_discoverable(self):
        try:
            adapter.Set("org.bluez.Adapter1", "Discoverable", GLib.Variant("b", True))
            adapter.Set("org.bluez.Adapter1", "Pairable", GLib.Variant("b", True))
            return True
        except Exception:
            raise RuntimeError(f"Failed to set discoverable")


    def discover_devices(self):
        """Scan for trusted Bluetooth devices and return a list of device Name and MAC addresses."""
        logger.info("Scanning for available Bluetooth devices...")
        def end_discovery():
            """Handler for end of discovery"""
            mainloop.quit()
            adapter.StopDiscovery()

        self.adapter_power(True)
        self.set_discoverable()
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
                    "device_path": path
                })
        self.devices = devices
        logger.info(f"Found ({len(devices)}) Bluetooth devices.")
        return devices
       


    def get_devices(self):
        """Gets the list of devices cached from last scan"""
        mng_objs = mngr.GetManagedObjects()       
        devices = []
        for path in mng_objs:
            device = mng_objs[path].get('org.bluez.Device1')
            if device and device.get('Name'):
                devices.append({
                    "device_path": path,
                    "name": device.get("Name"),
                    "address": device.get("Address"),
                    "alias": device.get("Alias"),
                    "icon": device.get("Icon"),
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
                            "device_path": device_path,
                            "adapter": device.Adapter,
                            "alias": device.Alias,
                            "address": device.Address,
                            "icon": device.Icon,
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
                                "device_path": path,
                                "name": device.get("Name"),
                                "address": device.get("Address"),
                                "alias": device.get("Alias"),
                                "icon": device.get("Icon"),
                                "connected":device.get("Connected")
                            }


    def parse_a2dp_config(self, codec, config):
        if codec == 0:  # SBC
            freq_map = {
                0b10000000: 16000,
                0b01000000: 32000,
                0b00100000: 44100,
                0b00010000: 48000
            }
            channel_map = {
                0b00001000: "Mono",
                0b00000100: "Dual Channel",
                0b00000010: "Stereo",
                0b00000001: "Joint Stereo"
            }

            freq = next((v for k, v in freq_map.items() if config[0] & k), None)
            channel = next((v for k, v in channel_map.items() if config[0] & k), None)
            return {"codec": "SBC", "rate": freq, "channels": channel}

        elif codec == 2:  # AAC
            freq_map = {
                0x80: 8000, 0x40: 11025, 0x20: 12000, 0x10: 16000,
                0x08: 22050, 0x04: 24000, 0x02: 32000, 0x01: 44100,
                0x00: 48000  # fallback
            }
            rate_byte = config[1]
            freq = freq_map.get(rate_byte & 0xFF, "Unknown")
            return {"codec": "AAC", "rate": freq, "channels": "Unknown"}

        return {"codec": f"Unknown ({codec})", "rate": "Unknown", "channels": "Unknown"}


    def _get_audio_pcm_info(self, device_path):
        try:
            mng_objs = mngr.GetManagedObjects()      
            for path in mng_objs:
                device = mng_objs[path].get('org.bluez.MediaTransport1')
                if device is not None and device.get('Device') == device_path:
                    return self.parse_a2dp_config(device.get('Codec'), device.get('Configuration'))

        except Exception as e:
            return f"Error retrieving PCM info: {e}"
        
    
    def get_audio_pcm_info(self):
        try:
            result = subprocess.check_output(["bluealsa-aplay", "-l"], text=True)
            lines = result.splitlines()
            for line in lines:
                if "A2DP" in line:
                    match = re.search(r"A2DP \((.*?)\): (.*?) (\d+) channels (\d+) Hz", line)
                    if match:
                        codec, fmt, channels, rate = match.groups()
                        return {
                            "codec": codec,
                            "format": fmt,
                            "channels": int(channels),
                            "rate": int(rate)
                        }
        except Exception as e:
            return {"error": str(e)}

    def get_player(self):
        """Gets device media player information"""
        player_path = None
        get_connected_device = self.get_device()
        
        try:
            mng_objs = mngr.GetManagedObjects()       
            for path, interfaces in mng_objs.items():
                if "org.bluez.MediaPlayer1" in interfaces:
                     player_path = path

            if player_path is not None and get_connected_device.get("device_path") in player_path:         
                device = bus.get(bluez_service, player_path)
                device_player = {
                                "status": device.Status,
                                "device_path": device.Device,
                                "player_path": player_path,
                                "name": device.Name,
                                "track": device.Track,
                                "type": device.Type,
                                "position": device.Position,
                            }
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

    
    def handle_incoming_device_request(self, incoming_device):
        """Handles incoming bluetooth request"""
        incoming_device_path = incoming_device.get("device_path")
        self.device_trust(incoming_device_path)
        devices = self.get_devices()
        
        for device in devices:
            device_path = device.get("device_path")
            if device_path != incoming_device_path:
                self.device_disconnect(device_path)


    def device_connect(self, device_path):
        """Connects to bluetooth device with address."""
        try:
            logger.debug(f"Attempting to connect to {device_path}...")

            get_new_device_path = None
            get_new_device = self.get_device(device_path)
            if get_new_device:
                get_new_device_path = device_path

            devices = self.get_devices()
            for device in devices:
                _device_path = device.get("device_path")
                if _device_path and _device_path != get_new_device_path:
                    self.device_disconnect(_device_path)

            if get_new_device_path:
                device = bus.get(bluez_service, get_new_device_path)
                self.device_trust(get_new_device_path)
                device.Connect()
            return get_new_device
        
        except Exception:
            raise RuntimeError(f"Failed to connect device {device_path}")


    def device_disconnect(self, device_path):
        """Disconnects a bluetooth device"""
        try:
            logger.debug(f"Disconnecting bluetooth device  {device_path}")
            device = bus.get(bluez_service, device_path)
            if hasattr(device, "Disconnect"):
                device.Disconnect()
            return True
        except Exception:
            raise RuntimeError(f"Failed to disconnect device {device_path}")
        

    def device_remove(self, device_path):
        """Removes a bluetooth devices."""
        try:
            logger.debug(f"Removing bluetooth device {device_path}")
            adapter.RemoveDevice(device_path)
            return True
        except Exception:
            raise RuntimeError(f"Failed to remove device {device_path}")
        

    def player_stop(self, device_path):
        """Bluetooth device player Stop command"""
        device = bus.get(bluez_service, device_path)
        if hasattr(device, "Stop"):
            device.Stop()
        return True
    

    def player_play(self, device_path):
        """Bluetooth device player Play command"""
        device = bus.get(bluez_service, device_path)
        if hasattr(device, "Play"):
            device.Play()
        return True


    def player_pause(self, device_path):
        """Bluetooth device player Pause command"""
        device = bus.get(bluez_service, device_path)
        if hasattr(device, "Pause"):
            device.Pause()
        return True


    def player_prev(self, device_path):
        """Bluetooth device player Previous command"""
        device = bus.get(bluez_service, device_path)
        if hasattr(device, "Previous"):
            device.Previous()
        return True
    

    def player_next(self, device_path):
        """Bluetooth device player Next command"""
        device = bus.get(bluez_service, device_path)
        if hasattr(device, "Next"):
            device.Next()
        return True


    
        
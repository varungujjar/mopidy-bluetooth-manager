
import logging
import subprocess
import threading
import os
import time
import re

logger = logging.getLogger(__name__)


class BluetoothCtlController():
    def __init__(self, core, config):
        self.config = config
        self.wait_time = 0
        self.connection_semaphore = threading.Semaphore(4)

    
    def bluetoothctl_cmd(self, command, wait_time=None):
        """Execute a command in the bluetoothctl environment and handle its output."""
        wait_time = wait_time or 0.1
        env = os.environ.copy()

        process = subprocess.Popen(
            ['/usr/bin/bluetoothctl'],
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            env=env
        )
        try:
            process.stdin.write(f"{command}\n")
            process.stdin.flush()
            time.sleep(wait_time)
            process.stdin.write("exit\n")
            process.stdin.flush()
            output, errors = process.communicate()
            if errors:
                print("Error executing command.", command, errors)
            return output
        except subprocess.TimeoutExpired:
            process.kill()
            _, errors = process.communicate()
            print("Command timeout. Bluetooth operation did not respond in time.", command, errors)
        finally:
            process.terminate()

    def on_start(self):
        self.bluetoothctl_cmd(f"system-alias {self.config['bluetooth']['name']}", 0)
        self.bluetoothctl_cmd("power on", 0)
        self.bluetoothctl_cmd("discoverable on", 0)
        self.bluetoothctl_cmd("pairable on", 0)
        self.bluetoothctl_cmd("agent on", 0)
        self.bluetoothctl_cmd("default-agent", 0)

    def scan_devices(self):
        """Scan for available Bluetooth devices and return a list of device Name and MAC addresses."""
        logger.debug("Scanning for available Bluetooth devices...")
        self.bluetoothctl_cmd("power on", 0)
        self.bluetoothctl_cmd("discoverable on", 0)
        self.bluetoothctl_cmd("scan on", 10)
        output = self.bluetoothctl_cmd("devices", 0)
        pattern = r'Device\s+([0-9A-Fa-f:]{17})\s+(.+)'
        matches = re.findall(pattern, output)
        devices = [{"mac": mac, "name": name} for mac, name in matches]
        return devices
    

    def connect_device(self, address):
        """Scan for available Bluetooth devices and return a list of device Name and MAC addresses."""
        logger.info(f"Attempting to connect to {address}...")
        # self.bluetoothctl_cmd(f"pair {address}", wait_time=1)
        self.bluetoothctl_cmd(f"trust {address}", wait_time=1)
        output = self.bluetoothctl_cmd(f"connect {address}", wait_time=5)
        print(output)
        if 'Connection successful' in output:
            logger.info(f"Successfully connected to {address}.")
            return True
        else:
            logger.error(f"Failed to connect to {address}.")
            return False


    def disconnect_device(self, address):
        """Scan for available Bluetooth devices and return a list of device Name and MAC addresses."""
        logger.info(f"Attempting to disconnect from {address}")
        output = self.bluetoothctl_cmd(
            f"disconnect {address}", 
            wait_time=5
        )
        print(output)
        if 'Successful disconnected' in output:
            logger.info(f"Successfully disconnected from {address}.")
            return True
        else:
            logger.error(f"Failed to disconnect from {address}.")
            return False
        

    def remove_device(self, address):
        """Scan for available Bluetooth devices and return a list of device Name and MAC addresses."""
        logger.info(f"Removing device {address}")
        output = self.bluetoothctl_cmd(f"remove {address}", wait_time=5)
        print(output)
        if 'Device has been removed' in output:
            logger.info(f"Successfully removed device {address}.")
            return True
        else:
            logger.error(f"Failed to remove device {address}.")
            return False    

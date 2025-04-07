import logging
import pykka
import subprocess
import os
import json
import threading
from pathlib import Path

from mopidy.models import Album, Artist, Track, TlTrack
from mopidy.types import PlaybackState, DurationMs
from mopidy.core.listener import CoreListener

logger = logging.getLogger(__name__)


class BluetoothFrontend(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core):
        super().__init__()
        self._config = config
        self.core = core
        self.running = True
        self.last_event = ""
        self.uri= ""
    

    def on_event(self, event, **kwargs):
        """Handle Mopidy events"""
        print(f"Received event: {event}")

    def on_start(self):
        # threading.Thread(target=self.start_librespot, daemon=True).start()
        # threading.Thread(target=self.handle_on_events, daemon=True).start()
        logger.info("Bluetooth renderer: Initialized")


    def on_stop(self):
        self.running = False
        logger.info("Librespot event listener stopped.")
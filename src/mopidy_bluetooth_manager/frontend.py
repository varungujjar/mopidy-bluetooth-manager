import logging
import pykka
import subprocess
import threading
import os
import time
import re

import tornado.escape
import tornado.ioloop
import tornado.web
import tornado.websocket

from .bluetoothctl import BluetoothCtlController 

import mopidy
from mopidy.models import Album, Artist, Track, TlTrack
from mopidy.types import PlaybackState, DurationMs
from mopidy.core.listener import CoreListener
from mopidy.core.actor import CoreProxy
from mopidy.internal import jsonrpc

from collections.abc import Awaitable
from typing import ClassVar

logger = logging.getLogger(__name__)


class BluetoothManager(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core):
        super().__init__()
        self.config = config
        self.core = core
        self.running = True
        self.last_event = ""
        self.uri= ""
        self.bluetooth_controller = BluetoothCtlController(core, config)


    def on_event(self, event, **kwargs):
        """Handle Mopidy events"""
        print(f"Received event: {event}")


    def on_start(self):
        # CoreListener.send("bluetooth_loaded")
        self.bluetooth_controller.on_start()
        logger.info("Bluetooth renderer: Initialized")


    def on_stop(self):
        self.running = False
        logger.info("Librespot event listener stopped.")


def make_jsonrpc_wrapper(core: CoreProxy, config) -> jsonrpc.Wrapper:
    return jsonrpc.Wrapper(
        objects={
            "bluetooth.scan": BluetoothCtlController(core, config).scan_devices,
            "bluetooth.connect": BluetoothCtlController(core, config).connect_device,
            "bluetooth.disconnect": BluetoothCtlController(core, config).disconnect_device,
            "bluetooth.remove": BluetoothCtlController(core, config).remove_device,
        },
    )


class JsonRpcHandler(tornado.web.RequestHandler):
    def initialize(
            self,core: CoreProxy,
            config,
            allowed_origins: set[str],
            csrf_protection: bool | None
            ) -> None:
        
        self.core = core
        self.config = config
        self.jsonrpc = make_jsonrpc_wrapper(core, config)
        self.allowed_origins = allowed_origins
        self.csrf_protection = csrf_protection

    def head(self) -> Awaitable[None] | None:
        self.set_extra_headers()
        self.finish()

    def post(self) -> Awaitable[None] | None:
        if self.csrf_protection:
            content_type = (
                self.request.headers.get("Content-Type", "").split(";")[0].strip()
            )
            if content_type != "application/json":
                self.set_status(415, "Content-Type must be application/json")
                return

            origin = self.request.headers.get("Origin")
            if origin is not None:
                # This request came from a browser and has already had its Origin
                # checked in the preflight request.
                self.set_cors_headers(origin)

        data = self.request.body
        if not data:
            return

        logger.debug("Received RPC message from %s: %r", self.request.remote_ip, data)

        try:
            self.set_extra_headers()
            response = self.jsonrpc.handle_json(tornado.escape.native_str(data))
            if response and self.write(response):
                logger.debug(
                    "Sent RPC message to %s: %r",
                    self.request.remote_ip,
                    response,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("HTTP JSON-RPC request error: %s", exc)
            self.write_error(500)

    def set_mopidy_headers(self) -> None:
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Mopidy-Version", mopidy.__version__.encode())

    def set_extra_headers(self) -> None:
        self.set_mopidy_headers()
        self.set_header("Accept", "application/json")
        self.set_header("Content-Type", "application/json; utf-8")

    def set_cors_headers(self, origin: str) -> None:
        self.set_header("Access-Control-Allow-Origin", f"{origin}")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")            



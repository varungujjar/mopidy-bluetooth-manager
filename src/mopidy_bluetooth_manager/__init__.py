import pathlib
import logging

from mopidy import config, ext
from mopidy.core.actor import CoreProxy
from mopidy.http.types import HttpConfig

from typing import TYPE_CHECKING, Any, cast
from .frontend import JsonRpcHandler

logger = logging.getLogger(__name__)


class Extension(ext.Extension):
    dist_name = "Mopidy-Bluetooth-Manager"
    ext_name = "bluetooth-manager"
    version = "0.1.0"

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()

        schema["name"] = config.String()
        schema["pincode"] = config.String()
        schema["autoconnect"] = config.Boolean()
        schema["initial-volume"] = config.String()
        schema["attach_audio_sink"] = config.String()
        return schema


    def setup(self, registry):
        from .frontend import BluetoothManager
        registry.add(
            "http:app", {"name": "bluetooth-manager", "factory": extension_factory}
        )
        registry.add("frontend", BluetoothManager)
        

def extension_factory(config, core):
    http_config = cast(HttpConfig, config["http"])
    return [
        (
            r"/rpc/?", 
            JsonRpcHandler, 
            {
                "core": core, 
                "config": config,
                "allowed_origins": http_config["allowed_origins"],
                "csrf_protection": http_config["csrf_protection"],
            }
        ),
    ]




    


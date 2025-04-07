import pathlib
from mopidy import config, ext

class Extension(ext.Extension):
    dist_name = "Mopidy-Bluetooth"
    ext_name = "bluetooth"
    version = "0.1.0"

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()

        schema["name"] = config.String()
        schema["pin"] = config.String()
        schema["autoconnect"] = config.Boolean()
        schema["initial-volume"] = config.String()
        schema["attach_audio_sink"] = config.String()
        return schema


    def setup(self, registry):
        from .frontend import BluetoothFrontend
        registry.add("frontend", BluetoothFrontend)

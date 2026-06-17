from __future__ import annotations

from .base import BPIOBase


class BPIOI2C(BPIOBase):
    def configure(
        self,
        speed: int = 100_000,
        clock_stretch: bool = False,
        **kwargs,
    ) -> bool:
        mode_configuration = kwargs.get("mode_configuration", {})
        mode_configuration.update(
            speed=speed,
            clock_stretch=clock_stretch,
        )
        kwargs["mode"] = "I2C"
        kwargs["mode_configuration"] = mode_configuration
        success = self.client.configuration_request(**kwargs)
        self.configured = bool(success)
        return bool(success)

    def start(self):
        if not self.config_check():
            return None
        return self.client.data_request(start_main=True)

    def stop(self):
        if not self.config_check():
            return None
        return self.client.data_request(stop_main=True)

    def write(self, data):
        if not self.config_check():
            return None
        return self.client.data_request(data_write=data)

    def read(self, num_bytes: int):
        if not self.config_check():
            return None
        return self.client.data_request(bytes_read=num_bytes)

    def transfer(self, write_data=None, read_bytes: int = 0):
        if not self.config_check():
            return None
        return self.client.data_request(
            start_main=True,
            data_write=write_data,
            bytes_read=read_bytes,
            stop_main=True,
        )

    def scan(self, start_addr: int = 0x08, end_addr: int = 0x77) -> list[int]:
        if not self.config_check():
            return []
        found = []
        for address in range(start_addr, end_addr + 1):
            result = self.transfer(write_data=[address << 1], read_bytes=0)
            if result is not False:
                found.append(address)
        return found

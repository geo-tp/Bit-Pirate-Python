from __future__ import annotations

from .base import BPIOBase


class BPIOSPI(BPIOBase):
    def configure(
        self,
        speed: int = 1_000_000,
        clock_polarity: bool = False,
        clock_phase: bool = False,
        chip_select_idle: bool = True,
        **kwargs,
    ) -> bool:
        mode_configuration = kwargs.get("mode_configuration", {})
        mode_configuration.update(
            speed=speed,
            data_bits=8,
            clock_polarity=clock_polarity,
            clock_phase=clock_phase,
            chip_select_idle=chip_select_idle,
        )
        kwargs["mode"] = "SPI"
        kwargs["mode_configuration"] = mode_configuration
        success = self.client.configuration_request(**kwargs)
        self.configured = bool(success)
        return bool(success)

    def select(self):
        if not self.config_check():
            return None
        return self.client.data_request(start_main=True)

    def deselect(self):
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

    def transfer(self, write_data, read_bytes: int | None = 0):
        if not self.config_check():
            return None
        return self.client.data_request(
            start_main=True,
            data_write=write_data,
            bytes_read=read_bytes or 0,
            stop_main=True,
        )

    def transfer_duplex(self, write_data, read_bytes: int | None = 0):
        if not self.config_check():
            return None
        return self.client.data_request(
            start_alt=True,
            data_write=write_data,
            bytes_read=read_bytes or 0,
            stop_main=True,
        )

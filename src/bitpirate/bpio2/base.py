from __future__ import annotations


class BPIOBase:
    def __init__(self, client):
        self.client = client
        self.configured = False

    def config_check(self) -> bool:
        if not self.configured:
            print("Interface not configured. Call configure() first.")
            return False
        return True

    def set_io_direction(self, direction_mask: int, direction: int):
        if not self.config_check():
            return None
        return self.client.configuration_request(
            io_direction_mask=direction_mask,
            io_direction=direction,
        )

    def set_io_value(self, value_mask: int, value: int):
        if not self.config_check():
            return None
        return self.client.configuration_request(
            io_value_mask=value_mask,
            io_value=value,
        )

    def get_status(self):
        return self.client.status_request()

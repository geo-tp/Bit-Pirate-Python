from __future__ import annotations


class BPIOGPIO:
    def __init__(self, client):
        self.client = client

    def configure_hiz(self) -> bool:
        return bool(self.client.configuration_request(mode="HiZ", mode_configuration={}))

    def set_direction(self, mask: int, outputs: int) -> bool:
        return bool(self.client.configuration_request(
            io_direction_mask=mask & 0xFF,
            io_direction=outputs & 0xFF,
        ))

    def write(self, mask: int, values: int) -> bool:
        return bool(self.client.configuration_request(
            io_value_mask=mask & 0xFF,
            io_value=values & 0xFF,
        ))

    def read(self) -> tuple[int, int]:
        status = self.client.status_request(io=True)
        if status is None:
            raise RuntimeError("No GPIO status response")
        return int(status["io_direction"]), int(status["io_value"])

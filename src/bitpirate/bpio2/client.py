"""Small synchronous BPIO2 v2.2 client used by the contributor kit.

This module implements the official BPIO2 FlatBuffers wire schema directly.
It intentionally supports the features exposed by ESP32 Bit Pirate's BPIO2
adapter: Status, Configuration, GPIO, SPI and I2C Data requests.
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from cobs import cobs
import flatbuffers
from flatbuffers import encode, number_types, packer
from flatbuffers.table import Table
import serial


# FlatBuffers union values from bpio.fbs.
REQ_STATUS = 1
REQ_CONFIGURATION = 2
REQ_DATA = 3
RESP_STATUS = 1
RESP_CONFIGURATION = 2
RESP_DATA = 3


class BPIOError(RuntimeError):
    """Raised for malformed or unexpected BPIO2 responses."""


def _root_table(data: bytes) -> Table:
    root = encode.Get(packer.uoffset, data, 0)
    return Table(data, root)


def _offset(table: Table, slot: int) -> int:
    return table.Offset(4 + slot * 2)


def _scalar(table: Table, slot: int, flags: Any, default: Any = 0) -> Any:
    off = _offset(table, slot)
    if off == 0:
        return default
    return table.Get(flags, off + table.Pos)


def _boolean(table: Table, slot: int, default: bool = False) -> bool:
    return bool(_scalar(table, slot, number_types.BoolFlags, default))


def _string(table: Table, slot: int) -> Optional[str]:
    off = _offset(table, slot)
    if off == 0:
        return None
    value = table.String(off + table.Pos)
    return value.decode("utf-8", errors="replace") if value else ""


def _table_field(table: Table, slot: int) -> Optional[Table]:
    off = _offset(table, slot)
    if off == 0:
        return None
    pos = table.Indirect(off + table.Pos)
    return Table(table.Bytes, pos)


def _byte_vector(table: Table, slot: int) -> bytes:
    off = _offset(table, slot)
    if off == 0:
        return b""
    start = table.Vector(off)
    length = table.VectorLen(off)
    return bytes(
        table.Get(number_types.Uint8Flags, start + index)
        for index in range(length)
    )


def _u32_vector(table: Table, slot: int) -> list[int]:
    off = _offset(table, slot)
    if off == 0:
        return []
    start = table.Vector(off)
    length = table.VectorLen(off)
    return [
        table.Get(number_types.Uint32Flags, start + index * 4)
        for index in range(length)
    ]


def _string_vector(table: Table, slot: int) -> list[str]:
    off = _offset(table, slot)
    if off == 0:
        return []
    start = table.Vector(off)
    length = table.VectorLen(off)
    result: list[str] = []
    for index in range(length):
        value = table.String(start + index * 4)
        result.append(value.decode("utf-8", errors="replace") if value else "")
    return result


def _finish_request(
    builder: flatbuffers.Builder,
    contents_type: int,
    contents: int,
    version_major: int,
    minimum_version_minor: int,
) -> bytes:
    # RequestPacket { version_major, minimum_version_minor,
    #                 contents_type, contents }
    builder.StartObject(4)
    builder.PrependUint8Slot(0, version_major, 0)
    builder.PrependUint16Slot(1, minimum_version_minor, 0)
    builder.PrependUint8Slot(2, contents_type, 0)
    builder.PrependUOffsetTRelativeSlot(3, contents, 0)
    root = builder.EndObject()
    builder.Finish(root)
    return bytes(builder.Output())


class BPIOClient:
    def __init__(
        self,
        port: str,
        baudrate: int = 3_000_000,
        timeout: float = 2.0,
        debug: bool = False,
        minimum_version: int = 2,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug
        self.version_flatbuffers_major = 2
        self.minimum_version_flatbuffers_minor = minimum_version
        self.serial_port = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=0.05,
            write_timeout=max(1.0, self.timeout),
        )
        self._rx_buffer = bytearray()
        self.serial_port.reset_input_buffer()

    def __enter__(self) -> "BPIOClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        port = getattr(self, "serial_port", None)
        if port is not None and port.is_open:
            port.close()

    def _read_frame(self) -> Optional[bytes]:
        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:
            delimiter = self._rx_buffer.find(0)
            if delimiter >= 0:
                encoded = bytes(self._rx_buffer[:delimiter])
                del self._rx_buffer[: delimiter + 1]
                if not encoded:
                    continue
                try:
                    return cobs.decode(encoded)
                except cobs.DecodeError as error:
                    raise BPIOError(f"COBS response decode failed: {error}") from error

            waiting = self.serial_port.in_waiting
            chunk = self.serial_port.read(waiting if waiting > 0 else 1)
            if chunk:
                self._rx_buffer.extend(chunk)

        return None

    def _exchange(self, request: bytes, expected_type: int) -> Optional[Table]:
        packet = cobs.encode(request) + b"\x00"
        if self.debug:
            print(f"TX decoded={len(request)} encoded={len(packet)}")
        self.serial_port.write(packet)
        self.serial_port.flush()

        response = self._read_frame()
        if response is None:
            print("Timeout waiting for response")
            return None
        if self.debug:
            print(f"RX decoded={len(response)}")

        root = _root_table(response)
        top_error = _string(root, 0)
        if top_error:
            print(f"Error: {top_error}")
            return None

        response_type = int(_scalar(root, 1, number_types.Uint8Flags, 0))
        if response_type != expected_type:
            raise BPIOError(
                f"Unexpected response type {response_type}, expected {expected_type}"
            )

        contents = _table_field(root, 2)
        if contents is None:
            raise BPIOError("Response packet has no contents")
        return contents

    def status_request(self, **kwargs: bool) -> Optional[dict[str, Any]]:
        status_ids = {
            "version": 1,
            "mode": 2,
            "pullup": 3,
            "psu": 4,
            "adc": 5,
            "io": 6,
            "disk": 7,
            "led": 8,
        }
        requested = [value for key, value in status_ids.items() if kwargs.get(key)]
        if not requested:
            requested = [0]  # All

        builder = flatbuffers.Builder(128)
        builder.StartVector(1, len(requested), 1)
        for item in reversed(requested):
            builder.PrependUint8(item)
        query = builder.EndVector()
        builder.StartObject(1)
        builder.PrependUOffsetTRelativeSlot(0, query, 0)
        contents = builder.EndObject()
        request = _finish_request(
            builder,
            REQ_STATUS,
            contents,
            self.version_flatbuffers_major,
            self.minimum_version_flatbuffers_minor,
        )
        table = self._exchange(request, RESP_STATUS)
        if table is None:
            return None

        return {
            "error": _string(table, 0),
            "version_flatbuffers_major": int(_scalar(table, 1, number_types.Uint8Flags, 0)),
            "version_flatbuffers_minor": int(_scalar(table, 2, number_types.Uint16Flags, 0)),
            "version_hardware_major": int(_scalar(table, 3, number_types.Uint8Flags, 0)),
            "version_hardware_minor": int(_scalar(table, 4, number_types.Uint8Flags, 0)),
            "version_firmware_major": int(_scalar(table, 5, number_types.Uint8Flags, 0)),
            "version_firmware_minor": int(_scalar(table, 6, number_types.Uint8Flags, 0)),
            "version_firmware_git_hash": _string(table, 7),
            "version_firmware_date": _string(table, 8),
            "modes_available": _string_vector(table, 9),
            "mode_current": _string(table, 10),
            "mode_pin_labels": _string_vector(table, 11),
            "mode_bitorder_msb": _boolean(table, 12),
            "mode_max_packet_size": int(_scalar(table, 13, number_types.Uint32Flags, 0)),
            "mode_max_write": int(_scalar(table, 14, number_types.Uint32Flags, 0)),
            "mode_max_read": int(_scalar(table, 15, number_types.Uint32Flags, 0)),
            "psu_enabled": _boolean(table, 16),
            "psu_set_mv": int(_scalar(table, 17, number_types.Uint32Flags, 0)),
            "psu_set_ma": int(_scalar(table, 18, number_types.Uint32Flags, 0)),
            "psu_measured_mv": int(_scalar(table, 19, number_types.Uint32Flags, 0)),
            "psu_measured_ma": int(_scalar(table, 20, number_types.Uint32Flags, 0)),
            "psu_current_error": _boolean(table, 21),
            "pullup_enabled": _boolean(table, 22),
            "adc_mv": _u32_vector(table, 23),
            "io_direction": int(_scalar(table, 24, number_types.Uint8Flags, 0)),
            "io_value": int(_scalar(table, 25, number_types.Uint8Flags, 0)),
            "disk_size_mb": float(_scalar(table, 26, number_types.Float32Flags, 0.0)),
            "disk_used_mb": float(_scalar(table, 27, number_types.Float32Flags, 0.0)),
            "led_count": int(_scalar(table, 28, number_types.Uint8Flags, 0)),
        }

    def configuration_request(self, **kwargs: Any) -> bool:
        builder = flatbuffers.Builder(512)

        mode_offset = builder.CreateString(str(kwargs["mode"])) if "mode" in kwargs else 0
        print_offset = (
            builder.CreateString(str(kwargs["print_string"]))
            if "print_string" in kwargs
            else 0
        )

        led_offset = 0
        if "led_color" in kwargs:
            colors = list(kwargs["led_color"])
            builder.StartVector(4, len(colors), 4)
            for color in reversed(colors):
                builder.PrependUint32(int(color))
            led_offset = builder.EndVector()

        config_offset = 0
        config = kwargs.get("mode_configuration")
        if config is not None:
            builder.StartObject(13)
            if "speed" in config:
                builder.PrependUint32Slot(0, int(config["speed"]), 20_000)
            if "data_bits" in config:
                builder.PrependUint8Slot(1, int(config["data_bits"]), 8)
            if "parity" in config:
                builder.PrependBoolSlot(2, bool(config["parity"]), False)
            if "stop_bits" in config:
                builder.PrependUint8Slot(3, int(config["stop_bits"]), 1)
            if "flow_control" in config:
                builder.PrependBoolSlot(4, bool(config["flow_control"]), False)
            if "signal_inversion" in config:
                builder.PrependBoolSlot(5, bool(config["signal_inversion"]), False)
            if "clock_stretch" in config:
                builder.PrependBoolSlot(6, bool(config["clock_stretch"]), False)
            if "clock_polarity" in config:
                builder.PrependBoolSlot(7, bool(config["clock_polarity"]), False)
            if "clock_phase" in config:
                builder.PrependBoolSlot(8, bool(config["clock_phase"]), False)
            if "chip_select_idle" in config:
                builder.PrependBoolSlot(9, bool(config["chip_select_idle"]), True)
            if "submode" in config:
                builder.PrependUint8Slot(10, int(config["submode"]), 0)
            if "tx_modulation" in config:
                builder.PrependUint32Slot(11, int(config["tx_modulation"]), 0)
            if "rx_sensor" in config:
                builder.PrependUint8Slot(12, int(config["rx_sensor"]), 0)
            config_offset = builder.EndObject()

        builder.StartObject(20)
        if mode_offset:
            builder.PrependUOffsetTRelativeSlot(0, mode_offset, 0)
        if config_offset:
            builder.PrependUOffsetTRelativeSlot(1, config_offset, 0)

        bool_fields = {
            "mode_bitorder_msb": 2,
            "mode_bitorder_lsb": 3,
            "psu_disable": 4,
            "psu_enable": 5,
            "pullup_disable": 8,
            "pullup_enable": 9,
            "led_resume": 14,
            "hardware_bootloader": 17,
            "hardware_reset": 18,
            "hardware_selftest": 19,
        }
        for key, slot in bool_fields.items():
            if key in kwargs:
                builder.PrependBoolSlot(slot, bool(kwargs[key]), False)

        if "psu_set_mv" in kwargs:
            builder.PrependUint32Slot(6, int(kwargs["psu_set_mv"]), 0)
        if "psu_set_ma" in kwargs:
            builder.PrependUint16Slot(7, int(kwargs["psu_set_ma"]), 300)
        for key, slot in (
            ("io_direction_mask", 10),
            ("io_direction", 11),
            ("io_value_mask", 12),
            ("io_value", 13),
        ):
            if key in kwargs:
                builder.PrependUint8Slot(slot, int(kwargs[key]), 0)
        if led_offset:
            builder.PrependUOffsetTRelativeSlot(15, led_offset, 0)
        if print_offset:
            builder.PrependUOffsetTRelativeSlot(16, print_offset, 0)

        contents = builder.EndObject()
        request = _finish_request(
            builder,
            REQ_CONFIGURATION,
            contents,
            self.version_flatbuffers_major,
            self.minimum_version_flatbuffers_minor,
        )
        table = self._exchange(request, RESP_CONFIGURATION)
        if table is None:
            return False
        error = _string(table, 0)
        if error:
            if self.debug:
                print(f"Configuration error: {error}")
            return False
        return True

    def data_request(
        self,
        start_main: bool = False,
        start_alt: bool = False,
        data_write: Optional[Iterable[int]] = None,
        bytes_read: int = 0,
        stop_main: bool = False,
        stop_alt: bool = False,
    ) -> bytes | None | bool:
        builder = flatbuffers.Builder(max(256, (len(data_write) if hasattr(data_write, "__len__") else 0) + 128))
        data_offset = 0
        if data_write is not None:
            payload = bytes(data_write)
            if payload:
                data_offset = builder.CreateByteVector(payload)

        builder.StartObject(6)
        if start_main:
            builder.PrependBoolSlot(0, True, False)
        if start_alt:
            builder.PrependBoolSlot(1, True, False)
        if data_offset:
            builder.PrependUOffsetTRelativeSlot(2, data_offset, 0)
        if bytes_read:
            builder.PrependUint16Slot(3, int(bytes_read), 0)
        if stop_main:
            builder.PrependBoolSlot(4, True, False)
        if stop_alt:
            builder.PrependBoolSlot(5, True, False)
        contents = builder.EndObject()

        request = _finish_request(
            builder,
            REQ_DATA,
            contents,
            self.version_flatbuffers_major,
            self.minimum_version_flatbuffers_minor,
        )
        table = self._exchange(request, RESP_DATA)
        if table is None:
            return False
        error = _string(table, 0)
        if error:
            if self.debug:
                print(f"Data request error: {error}")
            return False
        data = _byte_vector(table, 1)
        return data if data else None

    def print_status_response(self, status: dict[str, Any]) -> None:
        print(
            f"BPIO {status['version_flatbuffers_major']}."
            f"{status['version_flatbuffers_minor']} | "
            f"firmware {status['version_firmware_major']}."
            f"{status['version_firmware_minor']} | "
            f"mode {status['mode_current']}"
        )
        for label in status.get("mode_pin_labels", []):
            print(f"  {label}")
        print(
            f"Limits: packet={status['mode_max_packet_size']}, "
            f"write={status['mode_max_write']}, read={status['mode_max_read']}"
        )

    def show_status(self) -> None:
        status = self.status_request()
        if status is None:
            print("Failed to get status")
        else:
            self.print_status_response(status)

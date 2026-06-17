# Bit Pirate Python

Python clients for controlling [ESP32 Bit Pirate](https://github.com/geo-tp/ESP32-Bit-Pirate) through:

- USB serial CLI
- Wi-Fi WebSocket CLI
- BPIO2 binary GPIO, I2C, and SPI adapter mode

## Installation

```bash
pip install bit-pirate-python
```

The PyPI distribution is named `bit-pirate`; the Python import package is `bitpirate`.

## USB serial CLI

```python
from bitpirate import BitPirate

bp = BitPirate.auto_connect()
bp.start()
bp.change_mode("i2c")
bp.send("scan")
bp.wait()
print(bp.receive())
bp.stop()
```

A specific serial port can also be selected:

```python
from bitpirate import BitPirate

bp = BitPirate("/dev/ttyACM0")
```

## Wi-Fi CLI

```python
from bitpirate import BitPirateWifi

bp = BitPirateWifi("192.168.4.1")
bp.start()
bp.change_mode("uart")
bp.send("read")
print(bp.receive())
bp.stop()
```

## BPIO2

Switch ESP32 Bit Pirate to the BPIO2 USB adapter before opening the port.

```python
from bitpirate.bpio2 import BPIOClient

with BPIOClient("/dev/ttyACM0", timeout=3) as client:
    status = client.status_request()
    print(status)
```

Protocol helpers are available as `BPIOGPIO`, `BPIOI2C`, and `BPIOSPI`.
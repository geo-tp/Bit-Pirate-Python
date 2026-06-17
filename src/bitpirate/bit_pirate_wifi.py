import websocket
import time

class BitPirateWifi:
    """
    Class to interact with the ESP32 Bit Pirate over WiFi using the websocket connection.
    """

    def __init__(self, ip: str, timeout: float = 1.0):
        """
        Connect to the Bit Pirate over WebSocket.
        - ip: IP address of the Bit Pirate (e.g. "192.168.0.57")
        - timeout: read timeout in seconds
        """
        self.ip = ip
        self.timeout = timeout
        self.url = f"ws://{ip}/ws"
        self._buffer = bytearray()

        self.ws = websocket.WebSocket()
        self.ws.settimeout(timeout)
        self.ws.connect(self.url)

    def _pull_data(self, timeout: float = 0.1):
        """
        Pull any available data from the websocket into the internal buffer.
        """
        old_timeout = self.ws.gettimeout()
        self.ws.settimeout(timeout)
        try:
            while True:
                try:
                    data = self.ws.recv()
                    if data:
                        if isinstance(data, str):
                            data = data.encode("utf-8")
                        self._buffer += data
                    else:
                        break
                except websocket.WebSocketTimeoutException:
                    break
        finally:
            self.ws.settimeout(old_timeout)

    def _readline(self, timeout: float = 0.5) -> bytes:
        """
        Read a single line (ending with \\n) from the internal buffer,
        pulling from the websocket as needed.
        """
        deadline = time.time() + timeout
        while True:
            # Check if buffer already contains a complete line
            idx = self._buffer.find(b"\n")
            if idx != -1:
                line = bytes(self._buffer[: idx + 1])
                self._buffer = self._buffer[idx + 1 :]
                return line

            # Try to pull more data from the websocket
            remaining = deadline - time.time()
            if remaining <= 0:
                # Timeout – return whatever partial data we have
                if self._buffer:
                    data = bytes(self._buffer)
                    self._buffer.clear()
                    return data
                return b""

            self._pull_data(timeout=min(remaining, 0.1))

    @property
    def _in_waiting(self) -> int:
        """
        Number of bytes sitting in the internal buffer (pulls pending
        websocket frames first so the count is up-to-date).
        """
        self._pull_data(timeout=0.05)
        return len(self._buffer)

    def start(self, wake_attempts: int = 10):
        """
        Wake up the Bit Pirate and clear any residual data in the buffer.
        - wake_attempts: number of newline attempts to wake the Bit Pirate
        """
        self.flush()

        # In case the Bit Pirate is in a mode/shell
        self.send("n")
        self.wait()
        self.send("1")
        self.wait()

        # Send newlines to escape a mode config or other cmd config
        for _ in range(wake_attempts):
            self.ws.send("\n")

        self.wait()
        self.flush()

    def change_mode(self, mode: str):
        """
        Change the Bit Pirate mode.
        - mode string: "I2C", "SPI", "UART", etc.
        """
        self.send("m " + mode.lower())
        self.send("\n" * 10)  # select the default configuration
        self.wait()
        self.flush()

    def flush(self):
        """
        Clear the internal buffer and drain any pending websocket data.
        """
        self._buffer.clear()

        # Drain pending websocket frames
        old_timeout = self.ws.gettimeout()
        self.ws.settimeout(0.1)
        try:
            while True:
                try:
                    data = self.ws.recv()
                    if not data:
                        break
                except websocket.WebSocketTimeoutException:
                    break
        finally:
            self.ws.settimeout(old_timeout)

    def wait(self, delay: float = 0.3):
        """
        Wait for a period to allow the Bit Pirate to process commands.
        - delay: time in seconds to wait
        """
        time.sleep(delay)

    def send(self, data: str):
        """
        Send a command or data to the Bit Pirate.
        - data: command data string to send
        """
        if not data.endswith("\n"):
            data += "\n"
        self.ws.send(data)

    def receive(self, skip: int = 1, timeout: float = 0.5) -> list[str]:
        """
        Receive data from the Bit Pirate.
        - skip: number of lines to skip (e.g., echoes)
        - timeout: stop reading if no data is received for `timeout` seconds
        """
        self.clear_echoes(skip)

        result = []
        last_data_time = time.time()

        while True:
            if self._in_waiting:
                line = (
                    self._readline(timeout=timeout)
                    .decode("utf-8", errors="ignore")
                    .strip()
                )
                if line:
                    result.append(line)
                last_data_time = time.time()
            elif time.time() - last_data_time > timeout:
                break

        return result[0:-1] if result and result[-1].endswith(">") else result

    def receive_all(self, silence_timeout: float = 0.5) -> list[str]:
        """
        Receive all data from the Bit Pirate until a period of silence.
        - silence_timeout: time in seconds to wait for new data before
          considering the transmission complete.
        """
        lines = []
        last_data_time = time.time()

        while True:
            if self._in_waiting > 0:
                line = (
                    self._readline(timeout=silence_timeout)
                    .decode("utf-8", errors="ignore")
                    .strip()
                )
                if line:
                    if not line.endswith(">"):  # Ignore prompts
                        lines.append(line)
                    last_data_time = time.time()
            else:
                if time.time() - last_data_time > silence_timeout:
                    break
                time.sleep(0.05)

        return lines

    def receive_raw(self, silence_timeout: float = 0.5, max_bytes: int | None = None) -> bytes:
        """
        Receive raw bytes until silence_timeout seconds of silence.
        - silence_timeout: duration (s) without new data before stopping.
        - max_bytes: optional hard limit to avoid consuming too much data.
        Returns: bytes (raw binary stream received).
        """
        buf = bytearray()
        last_data_time = time.time()

        while True:
            self._pull_data(timeout=min(0.1, silence_timeout))

            if self._buffer:
                chunk = bytes(self._buffer)
                self._buffer.clear()
                buf += chunk
                last_data_time = time.time()
                if max_bytes is not None and len(buf) >= max_bytes:
                    return bytes(buf[:max_bytes])
            else:
                if time.time() - last_data_time > silence_timeout:
                    break

        return bytes(buf)

    def clear_echoes(self, lines: int = 1):
        """
        Clear echoed lines from the Bit Pirate.
        - lines: number of echoed lines to clear
        """
        for _ in range(lines):
            self._readline(timeout=self.timeout)

    def stop(self):
        """
        Close the Bit Pirate WebSocket connection.
        """
        try:
            self.ws.close()
        except Exception:
            pass

import serial
import time
import serial.tools.list_ports

class BitPirate:
    """
    Class to interact with the ESP32 Bit Pirate via serial interface.
    """
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    @classmethod
    def auto_connect(cls, baudrate: int = 115200, timeout: float = 1.0):
        """
        Try to automatically detect and connect to the Bit Pirate.
        """
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if "usb" in p.device.lower() or "tty" in p.device.lower():
                try:
                    ser = serial.Serial(p.device, baudrate=baudrate, timeout=timeout)
                    ser.write(b'\n')
                    response = ser.readline()
                    if response:
                        ser.close()
                        return cls(p.device, baudrate, timeout)
                except Exception:
                    pass

        raise RuntimeError("No ESP32 Bit Pirate found.")
    
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
            self.serial.write(b"\n")
        
        self.serial.flush()
        self.serial.timeout = 0.1
        responses = []
    
    def change_mode(self, mode: str):
        """
        Change the Bit Pirate mode.
        - mode string: "I2C", "SPI", "UART", etc.
        """
        self.send("m " + mode.lower())
        self.send("\n" * 10) # select the default configuration
        self.wait()
        self.flush()
    
    def flush(self):
        """
        Clear the input and output buffers.
        """
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()

        ## Flush the lines if any
        while True:
            line = self.serial.readline()
            if not line:
                break
   
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
        self.serial.write(data.encode("utf-8"))


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
            if self.serial.in_waiting:
                line = self.serial.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    result.append(line)
                last_data_time = time.time()  # reset timer
            elif time.time() - last_data_time > timeout:
                break

        return result[0:-1] if result and result[-1].endswith(">") else result

    
    def receive_all(self, silence_timeout: float = 0.5) -> list[str]:
        """
        Receive all data from the Bit Pirate until a period of silence.
        - silence_timeout: time in seconds to wait for new data before considering the transmission complete.
        """
        import time

        lines = []
        last_data_time = time.time()

        while True:
            if self.serial.in_waiting > 0:
                line = self.serial.readline().decode("utf-8", errors="ignore").strip()
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
        Reçoit des octets bruts jusqu'à un silence de 'silence_timeout' secondes.
        - silence_timeout : durée (s) sans nouveau byte avant d'arrêter.
        - max_bytes       : limite dure optionnelle pour éviter d'avaler trop de données.
        Retourne: bytes (flux binaire reçu).
        """
        import time

        buf = bytearray()
        last_data_time = time.time()

        # Assure un timeout non bloquant côté pySerial
        old_timeout = self.serial.timeout
        if old_timeout is None or old_timeout > silence_timeout:
            self.serial.timeout = min(0.1, silence_timeout)

        try:
            while True:
                # Lire ce qui est dispo; si rien, read() retourne b'' après 'timeout'
                chunk = self.serial.read(self.serial.in_waiting or 1024)
                if chunk:
                    buf += chunk
                    last_data_time = time.time()
                    if max_bytes is not None and len(buf) >= max_bytes:
                        return bytes(buf[:max_bytes])
                else:
                    # Pas de nouveau byte; vérifier le silence cumulé
                    if time.time() - last_data_time > silence_timeout:
                        break
        finally:
            # Restaurer le timeout précédent
            self.serial.timeout = old_timeout

        return bytes(buf)

    def clear_echoes(self, lines: int = 1):
        """
        Clear echoed lines from the Bit Pirate.
        - lines: number of echoed lines to clear
        """
        for _ in range(lines):
            self.serial.readline()
    
    def stop(self):
        """
        Close the bit pirate connection.
        """
        self.serial.close()
import re

class Helper:
    """
    Helper class with static methods for data extraction and manipulation.
    """

    @staticmethod
    def extractHexFromList(lines: list[str]) -> list[str]:
        """
        Extract all hexadecimal addresses of the form '0xNN' from a list of strings.
        Returns a sorted list without duplicates.
        """
        hex_values = set()
        pattern = re.compile(r"0x[0-9A-Fa-f]{2}")

        for line in lines:
            matches = pattern.findall(line)
            hex_values.update(matches)

        return sorted(hex_values)

    @staticmethod
    def extractSsidsFromList(lines: list[str]) -> list[str]:
        """
        Extract SSIDs from a list of strings from the scan cmd
        """
        ssids = []
        for line in lines:
            if "SSID:" in line:
                parts = line.split("|")
                for part in parts:
                    part = part.strip()
                    if part.startswith("SSID:"):
                        ssid = part.replace("SSID:", "").strip()
                        if ssid:
                            ssids.append(ssid)
        return ssids
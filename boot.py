import pycom
import os

pycom.heartbeat(False)
pycom.wifi_on_boot(False)
pycom.rgbled(0x000000)

uart = UART(0, baudrate=115200)
os.dupterm(uart)
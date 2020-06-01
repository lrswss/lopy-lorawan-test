#
# MicroPython script for LoPy/LoPy4 development boards to
# check LoRaWAN connectivity with TTN (OTAA and ABP mode)
#
# (c) 2020 Lars Wessels <software@bytebox.org>
# Published under MIT License
#

import uos
import pycom
from network import LoRa
import socket
import ubinascii
import struct
import utime

LED_OFF = const(0x000000)
LED_BLUE = const(0x0000ff)
LED_GREEN = const(0x00ff00)
LED_RED = const(0xff0000)
LED_YELLOW = const(0x7f7f00)
LED_PINK = const(0xFF0088)

# LoRA date rate (0 = SF12 to 5 = SF7)
LORA_DR = const(2)
LORA_DR_JOIN = const(2)

# optionally request acknowledge for every packet
# Note for TTN: ACK only works for all DR using OTAA; in ABP mode 
# ACKs will only be received for DR4 or DR5, since there seems to 
# be no way to set the TTN specific RX2 window (869.525MHz, SF9)
# https://www.thethingsnetwork.org/docs/lorawan/frequency-plans.html
LORA_ACK = True

# Use OTAA or ABP
LORA_OTAA = True

# OTAA keys (copy & paste from *YOUR* TTN console)
OTAA_APP_EUI = '70B3D57ED002FFFF'
OTAA_APP_KEY = 'F32ADC1EDD72A50C42CE8942B3FFFFFF' 
OTAA_JOIN_TIMEOUT = 30

# ABP keys (copy & paste from *YOUR* TTN console)
ABP_DEV_ADDR = '26010000'
ABP_NET_KEY = '07966421204E8FAB6C0835079EFFFFFF'
ABP_APP_KEY = 'A87CC988EB3BD948A7FBDF7423FFFFFF'


def event_handler(lora):
    """ event handler printing stats of last transmission and optional ack from gateway """
    global LORA_ACK, RX_EVENT
    events = lora.events()
    if events == 0:
        return
    stats = lora.stats()
    if events & LoRa.TX_PACKET_EVENT:
        msg = "LoRa stats: TX[sf={}, airtime={}ms, count={}, retries={}]".format(
            12-stats[4], stats[7], stats[8], stats[5])
    if events & LoRa.TX_PACKET_EVENT and LORA_ACK or events & LoRa.RX_PACKET_EVENT:
        msg += " RX[sf={}, rssi={}dBm, snr={}dB]".format(12-stats[3], stats[1], stats[2])
        RX_EVENT = True
        flash_led(LED_PINK, 0.1, 0.3, 2)
    print(msg)
    if events & LoRa.TX_FAILED_EVENT:
        print("Warning: no ACK after {} attempts".format(stats[5]))

def flash_led(color=LED_RED, on=0.1, pause=0.2, repeat=1):
    """ flash RGB LED on LoPy """
    for _ in range(0, repeat):
        pycom.rgbled(color)
        utime.sleep(on)
        pycom.rgbled(LED_OFF)
        utime.sleep(pause)

# setup LoRaWAN stack with presets for Europe (868 MHz)
print("\nInit LoRaWAN stack on {} running {}...".format(uos.uname()[0], uos.uname()[2]))
lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868)
print("LoRa DevEUI: {}".format(ubinascii.hexlify(lora.mac()).upper().decode()))

# join network either using OTAA or ABP
if LORA_OTAA:
    app_eui = ubinascii.unhexlify(OTAA_APP_EUI)
    app_key = ubinascii.unhexlify(OTAA_APP_KEY)
    lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0, dr=LORA_DR_JOIN)
    print("Starting OTAA join...", end="")
    otaa_timer = 0
    start_join = utime.ticks_ms()
    while not lora.has_joined() and otaa_timer < OTAA_JOIN_TIMEOUT:
        otaa_timer = int(utime.ticks_diff(utime.ticks_ms(), start_join)/1000)
        print(".", end="")
        flash_led(LED_BLUE, 0.1, 0.9)
    if lora.has_joined():
        print("OK.")
        flash_led(LED_BLUE, 1.0, 1.0)
    else:
        print("timeout, failed!")
        flash_led(LED_RED, 1.0, 1.0)
else:
    print("ABP mode with preshared keys")
    dev_addr = struct.unpack(">l", ubinascii.unhexlify(ABP_DEV_ADDR))[0]
    nwk_swkey = ubinascii.unhexlify(ABP_NET_KEY)
    app_swkey = ubinascii.unhexlify(ABP_APP_KEY)
    lora.join(activation=LoRa.ABP, auth=(dev_addr, nwk_swkey, app_swkey))
    lora.add_channel(3, frequency=867100000, dr_min=0, dr_max=5)
    lora.add_channel(4, frequency=867300000, dr_min=0, dr_max=5)
    lora.add_channel(5, frequency=867500000, dr_min=0, dr_max=5)
    lora.add_channel(6, frequency=867700000, dr_min=0, dr_max=5)
    lora.add_channel(7, frequency=867900000, dr_min=0, dr_max=5)

# create a LoRa socket
s = socket.socket(socket.AF_LORA, socket.SOCK_RAW)

# set the LoRaWAN data rate
s.setsockopt(socket.SOL_LORA, socket.SO_DR, LORA_DR)

# settings for ACK after TX
s.setsockopt(socket.SOL_LORA, socket.SO_CONFIRMED, LORA_ACK)

# install callback handler for TX/RX events
lora.callback(trigger=(LoRa.RX_PACKET_EVENT|LoRa.TX_PACKET_EVENT), handler=event_handler)

# send data every 30 seconds
counter = 0
while True and lora.has_joined():
    counter += 1
    RX_EVENT = False
    print("Sending uplink packet {} with SF{}{}...".format(
        counter, 12-LORA_DR, ' asking for ACK' if LORA_ACK else ''), end="")
    try:
        s.setblocking(True)
        s.settimeout(10)
        flash_led(LED_GREEN, 0.1, 0.3, 2)
        s.send(bytes([counter]))
        print("OK.")
    except socket.timeout:
        flash_led(LED_RED, 1.0, 1.0, 2)
        print("Timeout!")
    s.setblocking(False)
    rx_pkt, rx_port = s.recvfrom(64)
    if RX_EVENT and len(rx_pkt) == 0:
        print("ACK received.")
    elif len(rx_pkt) > 0:
        print("Received downlink packet on port {}: {}".format(rx_port, rx_pkt))
    else:
        print("No downlink packet received.")

    utime.sleep(1) # waiting for callback message
    print("Waiting 30 seconds...")
    flash_led(LED_YELLOW, 0.2, 0.8, 29)

pycom.rgbled(LED_RED)

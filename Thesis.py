import serial, binascii
import time

ser = serial.Serial(
port='COM4', 
baudrate = 9600,
parity=serial.PARITY_NONE,
stopbits=serial.STOPBITS_ONE,
bytesize=serial.EIGHTBITS,
timeout=.5

)
ser.close()
ser.open()

try:
    while True:
        if ser.in_waiting > 0:  # Check if data is available
            data = ser.readline(1024)  # Read and decode data\
            hex_data = binascii.hexlify(data).decode('utf-8')
            print("RFID Data:", hex_data)  # Print the scanned RFID tag
except KeyboardInterrupt:
    print("Exiting...")
finally:
    ser.close()  # Close the serial port
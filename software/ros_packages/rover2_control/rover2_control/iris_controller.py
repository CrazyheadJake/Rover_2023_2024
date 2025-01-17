#!/usr/bin/env python

#####################################
# Node Information        
#####################################
# 
# Name: iris_controller
#
# Subscribed to:
# 
# Publishes to: 
# - iris_status (IrisStatusMessage)
# - command_control/iris_drive (DriveCommandMessage)
#

#####################################
# Imports
#####################################
# Python native imports
import rclpy
from rclpy.node import Node

from time import time, sleep

import serial.rs485
import minimalmodbus

# Custom Imports
from rover2_control_interface.msg import DriveCommandMessage, IrisStatusMessage

#####################################
# Global Variables
#####################################
NODE_NAME = "iris_controller"

DEFAULT_PORT = "/dev/rover/ttyIRIS"
DEFAULT_BAUD = 115200

DEFAULT_DRIVE_COMMAND_TOPIC = "command_control/iris_drive"
DEFAULT_IRIS_STATUS_TOPIC = "iris_status"

DEFAULT_HERTZ = 10
COMMUNICATIONS_TIMEOUT = 0.15  # Seconds

MODBUS_ID = 1

RX_DELAY = 0.01
TX_DELAY = 0.01

SBUS_VALUES = {
    "SBUS_MAX": 1811,
    "SBUS_MID": 991,
    "SBUS_MIN": 172,
    "SBUS_RANGE": 820.0,

    "SBUS_DEADZONE": 5
}

MODBUS_REGISTERS = {
    "LEFT_STICK_Y_AXIS": 0,
    "RIGHT_STICK_Y_AXIS": 1,
    "RIGHT_STICK_X_AXIS": 2,
    "LEFT_STICK_X_AXIS": 3,
    "LEFT_POT": 4,
    "S1_POT": 5,
    "S2_POT": 6,
    "RIGHT_POT": 7,
    "SA_SWITCH": 8,
    "SB_SWITCH": 9,
    "SC_SWITCH": 10,
    "SD_SWITCH": 11,
    "SE_SWITCH": 12,
    "SF_SWITCH": 13,
    "SG_SWITCH": 14,
    "SH_SWITCH": 15,

    "VOLTAGE_24V": 16,
    "VOLTAGE_5V": 17,
    "USB_VOLTAGE_5V": 18,
    "VOLTAGE_3V3": 19
}

REGISTER_STATE_MAPPING = {
    "IGNORE_CONTROL": "SF_SWITCH",
    "DRIVE_VS_ARM": "SE_SWITCH"
}

IRIS_LAST_SEEN_TIMEOUT = 1  # seconds


#####################################
# IrisController Class Definition
#####################################
class IrisController(Node):
    def __init__(self):
        super().__init__(NODE_NAME)

        self.port = self.declare_parameter('~port', DEFAULT_PORT).value
        self.baud = self.declare_parameter('~baud', DEFAULT_BAUD).value

        self.drive_command_publisher_topic = self.declare_parameter('~drive_command_topic', DEFAULT_DRIVE_COMMAND_TOPIC).value
        self.iris_status_publisher_topic = self.declare_parameter('~iris_status_topic', DEFAULT_IRIS_STATUS_TOPIC).value

        self.wait_time = 1.0 / self.declare_parameter('~hertz', DEFAULT_HERTZ).value

        self.iris = minimalmodbus.Instrument(self.port, MODBUS_ID)
        self.__setup_minimalmodbus_for_485()

        self.drive_command_publisher = self.create_publisher(DriveCommandMessage, self.drive_command_publisher_topic, 1)
        self.iris_status_publisher = self.create_publisher(IrisStatusMessage, self.iris_status_publisher_topic, 1)

        self.registers = []

        self.iris_connected = False

        self.iris_last_seen_time = time()

        self.timer = self.create_timer(self.wait_time, self.main_loop)

    def __setup_minimalmodbus_for_485(self):
        self.iris.serial = serial.rs485.RS485(self.port, baudrate=self.baud, timeout=COMMUNICATIONS_TIMEOUT)
        self.iris.serial.rs485_mode = serial.rs485.RS485Settings(rts_level_for_rx=1, rts_level_for_tx=0,
                                                                 delay_before_rx=RX_DELAY, delay_before_tx=TX_DELAY)

    def main_loop(self):
        try:
            self.read_registers()
            self.broadcast_drive_if_current_mode()
            self.broadcast_arm_if_current_mode()
            self.broadcast_iris_status()

        except Exception as error:
            print(f"IRIS: Error occurred: {error}")

        if (time() - self.iris_last_seen_time) > IRIS_LAST_SEEN_TIMEOUT:
            print(f"Iris not seen for {IRIS_LAST_SEEN_TIMEOUT} seconds. Exiting.")
            self.destroy_node()
            return  # Exit so respawn can take over

    def read_registers(self):
        try:
            self.registers = self.iris.read_registers(0, len(MODBUS_REGISTERS))
            self.iris_last_seen_time = time()
        except Exception as error:
            self.iris_connected = False

    def broadcast_drive_if_current_mode(self):
        if self.registers[MODBUS_REGISTERS[REGISTER_STATE_MAPPING["DRIVE_VS_ARM"]]] < SBUS_VALUES["SBUS_MID"]:
            command = DriveCommandMessage()

            left_y_axis = self.registers[MODBUS_REGISTERS["LEFT_STICK_Y_AXIS"]]
            right_y_axis = self.registers[MODBUS_REGISTERS["RIGHT_STICK_Y_AXIS"]]

            if left_y_axis == 0 and right_y_axis == 0:
                command.controller_present = False
                command.ignore_drive_control = True
                command.drive_twist.linear.x = 0.0
                command.drive_twist.angular.z = 0.0
            else:

                left = (left_y_axis - SBUS_VALUES["SBUS_MID"]) / SBUS_VALUES[
                    "SBUS_RANGE"]

                right = (right_y_axis - SBUS_VALUES["SBUS_MID"]) / SBUS_VALUES[
                    "SBUS_RANGE"]

                command.controller_present = True
                command.ignore_drive_control = \
                    self.registers[MODBUS_REGISTERS[REGISTER_STATE_MAPPING["IGNORE_CONTROL"]]] > SBUS_VALUES["SBUS_MID"]
                command.drive_twist.linear.x = (left + right) / 2.0
                command.drive_twist.angular.z = (right - left) / 2.0

            self.drive_command_publisher.publish(command)

    def broadcast_arm_if_current_mode(self):
        if self.registers[MODBUS_REGISTERS[REGISTER_STATE_MAPPING["DRIVE_VS_ARM"]]] > \
                        SBUS_VALUES["SBUS_MIN"] + SBUS_VALUES["SBUS_DEADZONE"]:
            print("Arm")

    def broadcast_iris_status(self):
        status_message = IrisStatusMessage()
        status_message.iris_connected = True
        status_message.voltage_24v = self.registers[MODBUS_REGISTERS["VOLTAGE_24V"]]
        self.iris_status_publisher.publish(status_message)


def main(args=None):
    rclpy.init(args=args)
    iris = IrisController()
    rclpy.spin(iris)
    iris.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()

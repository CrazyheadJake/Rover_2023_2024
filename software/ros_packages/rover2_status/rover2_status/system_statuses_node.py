#!/usr/bin/env python

#####################################
# Node Information        
#####################################
# 
# Name: rover_status
#
# Subscribed to:
# - update_requested (Empty)
# - /rover_control/iris_status (IrisStatusMessage)
# - /rover_control/drive_status/left (DriveStatusMessage)
# - /rover_control/drive_status/right (DriveStatusMessage)
# - /rover_control/drive_status/rear (DriveStatusMessage)
# - /rover_odometry/gps/sentence (Sentence)
# - /rover_control/command_control/iris_drive (DriveCommandMessage)
#
# Publishes to:
# - battery_status (BatteryStatusMessage)
# - camera_status (CameraStatuses)
# - wheel_status (WheelStatuses)
# - frsky_status (FrSkyStatus)
# - gps_status (GPSInfo)
# - jetson_status (JetsonInfo)
# - misc_status (MiscStatuses)
#

#####################################
# Imports
#####################################
# Python native imports
import rclpy
from rclpy.node import Node
import os.path
import psutil
import pynmea2
import subprocess
from rover2_status_interface.msg import BatteryStatusMessage, CameraStatuses, WheelStatuses, FrSkyStatus, GPSInfo, MiscStatuses, JetsonInfo, MotorStatus
from rover2_control_interface.msg import DriveCommandMessage, DriveStatusMessage, IrisStatusMessage
from std_msgs.msg import Empty
from nmea_msgs.msg import Sentence
from time import time


#####################################
# Global Variables
#####################################
# Publishers
DEFAULT_BATTERY_TOPIC_NAME = "battery_status"
DEFAULT_CAMERA_TOPIC_NAME = "camera_status"
DEFAULT_WHEEL_TOPIC_NAME = "wheel_status"
DEFAULT_FRSKY_TOPIC_NAME = "frsky_status"
DEFAULT_GPS_TOPIC_NAME = "gps_status"
DEFAULT_JETSON_TOPIC_NAME = "jetson_status"
DEFAULT_MISC_TOPIC_NAME = "misc_status"
##############created motor_status topic
# DEFAULT_MOTOR_TOPIC_NAME = "motor_status"
##############16 Feb 2019
MAX_JETSON_UPDATE_HERTZ = 0.2
MAX_IRIS_UPDATE_HERTZ = 0.2

# Subscribers
DEFAULT_REQUEST_UPDATE_TOPIC_NAME = "update_requested"
DEFAULT_IRIS_STATUS_TOPIC_NAME = "/rover_control/iris_status"
DEFAULT_BOGIE_LEFT_TOPIC_NAME = '/rover_control/drive_status/left'
DEFAULT_BOGIE_RIGHT_TOPIC_NAME = '/rover_control/drive_status/right'
DEFAULT_BOGIE_REAR_TOPIC_NAME = '/rover_control/drive_status/rear'
DEFAULT_GPS_NMEA_TOPIC_NAME = '/rover_odometry/gps/sentence'

NODE_NAME = 'SystemStatuses'
DEFAULT_HERTZ = 10


#####################################
# SystemStatuses Class Definition
#####################################
class SystemStatuses(Node):
    def __init__(self):
        super().__init__(NODE_NAME)

        # Camera path locations
        self.system_path_locations = [
            '/dev/rover/camera_zed',
            '/dev/rover/camera_undercarriage',
            '/dev/rover/camera_chassis',
            '/dev/rover/camera_main_navigation'
        ]

        # filesystem paths for EMMC [0] and NVME_SSD [1]
        # -- UPDATE [1] FOR JETSON --
        self.file_systems_EMMC_NVMe_SSD = [
            '/',
            '/dev/shm'
        ]

        self.wait_time = 1.0 / self.declare_parameter("~hertz", DEFAULT_HERTZ).value

        # Get Topic Names
        self.battery_topic_name = self.declare_parameter("~pub_battery_status_topic", DEFAULT_BATTERY_TOPIC_NAME).value
        self.camera_topic_name = self.declare_parameter("~pub_camera_status_topic", DEFAULT_CAMERA_TOPIC_NAME).value
        self.wheel_topic_name = self.declare_parameter("~pub_wheel_status_topic", DEFAULT_WHEEL_TOPIC_NAME).value
        self.frsky_topic_name = self.declare_parameter("~pub_frsky_status_topic", DEFAULT_FRSKY_TOPIC_NAME).value
        self.gps_topic_name = self.declare_parameter("~pub_gps_status_topic", DEFAULT_GPS_TOPIC_NAME).value
        self.jetson_topic_name = self.declare_parameter("~pub_jetson_status_topic", DEFAULT_JETSON_TOPIC_NAME).value
        self.misc_topic_name = self.declare_parameter("~pub_misc_status_topic", DEFAULT_MISC_TOPIC_NAME).value
        
        # Subscribers
        self.request_update_topic_name = self.declare_parameter("~sub_request_update_status_topic", DEFAULT_REQUEST_UPDATE_TOPIC_NAME).value
        self.iris_status_topic_name = self.declare_parameter("~sub_iris_status_topic", DEFAULT_IRIS_STATUS_TOPIC_NAME).value
        self.bogie_left_topic_name = self.declare_parameter("~sub_bogie_left_topic", DEFAULT_BOGIE_LEFT_TOPIC_NAME).value
        self.bogie_right_topic_name = self.declare_parameter("~sub_bogie_right_topic", DEFAULT_BOGIE_RIGHT_TOPIC_NAME).value
        self.bogie_rear_topic_name = self.declare_parameter("~sub_bogie_rear_topic", DEFAULT_BOGIE_REAR_TOPIC_NAME).value
        self.gps_nmea_topic_name = self.declare_parameter("~sub_gps_nmea_topic", DEFAULT_GPS_NMEA_TOPIC_NAME).value

        # init all publisher functions
        self.pub_battery = self.create_publisher(BatteryStatusMessage, self.battery_topic_name, 1)
        self.pub_camera = self.create_publisher(CameraStatuses, self.camera_topic_name, 1)
        self.pub_wheel = self.create_publisher(WheelStatuses, self.wheel_topic_name, 1)
        self.pub_FrSky = self.create_publisher(FrSkyStatus, self.frsky_topic_name, 1)
        self.pub_GPS = self.create_publisher(GPSInfo, self.gps_topic_name, 1)
        self.pub_jetson = self.create_publisher(JetsonInfo,self.jetson_topic_name,  1)
        self.pub_Misc = self.create_publisher(MiscStatuses, self.misc_topic_name, 1)

        # Subscribers
        self.request_update_subscriber = self.create_subscription(Empty, self.request_update_topic_name, self.on_update_requested, 1)

        # Manual update variable
        self.manual_update_requested = False

        # init all message variables
        self.battery_message = BatteryStatusMessage()
        self.camera_msg = CameraStatuses()
        self.wheel_msg = WheelStatuses()
        self.FrSky_msg = FrSkyStatus()
        self.GPS_msg = GPSInfo()
        self.jetson_msg = JetsonInfo()
        self.misc_msg = MiscStatuses()
#############initiate motor_msg
        self.motor_msg = MotorStatus()
#############16 February 2019

        # init all message values
        self.__pull_new_message_values()
        self.__instantiate_subscribers()

        # init all previous values
        self.__update_all_previous_values()
        self.last_jetson_message_sent = time()
        self.last_iris_message_sent = time()

        self.timer = self.create_timer(self.wait_time, self.main_loop)

    # init all RoverSysMessage values
    def __pull_new_message_values(self):
        self.__set_arm_connection_status()
        self.__set_arm_end_effector_connection_statuses()
        self.__set_cameras()
        self.__set_sample_containment_connection_status()
        self.__set_tower_connection_status()
        self.__set_chassis_pan_tilt_connection_status()
        self.__set_jetson_usage_information()
        self.__set_frsky_controller_connection_status()
#############Initiate motor message values
        # self.__set_motor_status()
#############16 February 2019

    # Pulls the UTC GPS Information (WIP v2.0)
    def __set_gps_info(self, data):
        self.GPS_msg.gps_connected = True
        try:
            self.Nmea_Message = pynmea2.parse(data.sentence)
        except Exception as e:
            return

        if self.Nmea_Message.sentence_type == 'GGA':
            if int(self.Nmea_Message.gps_qual) != 0:
                self.GPS_msg.gps_fix = True
            else:
                self.GPS_msg.gps_fix = False
            self.GPS_msg.num_satellites = int(self.Nmea_Message.num_sats)
            self.GPS_msg.horizontal_dilution = float(self.Nmea_Message.horizontal_dil)
        if self.Nmea_Message.sentence_type == 'VTG':
            try:
                self.GPS_msg.kmph = float(self.Nmea_Message.spd_over_grnd_kmph)
            except Exception as e:
                pass

            if self.Nmea_Message.true_track is not None:
                self.GPS_msg.gps_heading = float(self.Nmea_Message.true_track)
            else:
                self.GPS_msg.gps_heading = -1.0

    # Instantiates all subscriber methods
    def __instantiate_subscribers(self):
        # Iris Status Subscriber
        self.iris_status_sub = self.create_subscription(IrisStatusMessage, self.iris_status_topic_name, self.__iris_status_callback, 1)

        # Bogie Wheel Subscribers
        self.bogie_left_sub = self.create_subscription(DriveStatusMessage, self.bogie_left_topic_name, self.__left_wheel_callback, 1)
        self.bogie_right_sub = self.create_subscription(DriveStatusMessage, self.bogie_right_topic_name, self.__right_wheel_callback, 1)
        self.bogie_rear_sub = self.create_subscription(DriveStatusMessage, self.bogie_rear_topic_name, self.__rear_wheel_callback, 1)
        # GPS NMEA subscriber
        self.gps_nmea_sub = self.create_subscription(Sentence, self.gps_nmea_topic_name, self.__set_gps_info, 1)

    def __iris_status_callback(self, data):
        self.battery_message.battery_voltage = data.voltage_24v

    def __left_wheel_callback(self, data):
        self.wheel_msg.front_left = data.first_motor_connected
        self.wheel_msg.middle_left = data.second_motor_connected

    def __right_wheel_callback(self, data):
        self.wheel_msg.front_right = data.first_motor_connected
        self.wheel_msg.middle_right = data.second_motor_connected

    def __rear_wheel_callback(self, data):
        self.wheel_msg.rear_left = data.first_motor_connected
        self.wheel_msg.rear_right = data.second_motor_connected

    # Checks arm connection status (WIP)
    def __set_arm_connection_status(self):
        self.misc_msg.arm_connection_status = False

    # Checks Arm End Effector Connection Statuses (WIP)
    def __set_arm_end_effector_connection_statuses(self):
        self.misc_msg.arm_end_effector_connection_statuses = False

    # Sets the Camera values (zed, undercarriage, chassis, and main_nav
    def __set_cameras(self):
            # Check if camera_zed is found
            self.camera_msg.camera_zed = os.path.exists(self.system_path_locations[0])
            # Check if camera_undercarriage is found
            self.camera_msg.camera_undercarriage = os.path.exists(self.system_path_locations[1])
            # Check if camera_chassis is found
            self.camera_msg.camera_chassis = os.path.exists(self.system_path_locations[2])
            # Check if camera_main_navigation is found
            self.camera_msg.camera_main_navigation = os.path.exists(self.system_path_locations[3])

    # Checks Sample Containment Connection Status (WIP)
    def __set_sample_containment_connection_status(self):
        self.misc_msg.sample_containment_connection_status = False

    def __set_tower_connection_status(self):
        self.misc_msg.tower_connection_status = False

    # Checks Tower Connection Status (WIP)
    def __set_chassis_pan_tilt_connection_status(self):
        self.misc_msg.chassis_pan_tilt_connection_status = False

    # Get Jetson Statuses (WIP)
    def __set_jetson_usage_information(self):
        self.jetson_msg.jetson_cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        self.jetson_msg.jetson_ram = mem.percent
        self.jetson_msg.jetson_emmc = self.__used_percent_fs(self.file_systems_EMMC_NVMe_SSD[0])
        self.jetson_msg.jetson_nvme_ssd = self.__used_percent_fs(self.file_systems_EMMC_NVMe_SSD[1])

        # Temperature
        # This try except causes a bunch of annoying messages, but lets it run on non-jetson devices
        # sets to -1.0 if sensor fails to give it a default value notifying failure to pull
        try:
            sensor_temperatures = subprocess.check_output("sensors | grep temp", shell=True)
            parsed_temps = sensor_temperatures.replace("\xc2\xb0C","").replace("(crit = ","").replace("temp1:","")\
                .replace("\n", "").replace("+", "").split()
            self.jetson_msg.jetson_gpu_temp = float(parsed_temps[4])
        except subprocess.CalledProcessError:
            print('sensors call failed (potential reason: on VM)')
            self.jetson_msg.jetson_gpu_temp = -1.0

    # EMMC and NVMe_SSD used % calculation
    def __used_percent_fs(self, pathname):
        statvfs = os.statvfs(pathname)
        # percentage :: USED:
        #   used amount: blocks - bfree
        #   used%: used_amount / (used_amount + bavail)
        used_available = (statvfs.f_frsize * statvfs.f_blocks / 1024) - (statvfs.f_frsize * statvfs.f_bfree / 1024.0)
        used_percent = used_available / (used_available + (statvfs.f_frsize * statvfs.f_bavail / 1024.0))
        # Round 4 for 2 decimal accuracy
        value = 100 * round(used_percent, 4)
        return value

    # Check FrSky Controller Connection Status (WIP)
    def __set_frsky_controller_connection_status(self):
        self.create_subscription(DriveCommandMessage, '/rover_control/command_control/iris_drive', self.__frsky_callback, 1)

    def __frsky_callback(self, data):
        self.FrSky_msg.frsky_controller_connection_status = data.controller_present

    # Used mainly for init, sets all previous values in one go
    def __update_all_previous_values(self):
        self.__set_previous_battery_values()
        self.__set_previous_camera_values()
        self.__set_previous_jetson_values()
        self.__set_previous_frsky_value()
        self.__set_previous_wheel_values()
        self.__set_previous_gps_values()
        self.__set_previous_misc_values()

    def __set_previous_camera_values(self):
        self.previous_camera_zed = self.camera_msg.camera_zed
        self.previous_camera_undercarriage = self.camera_msg.camera_undercarriage
        self.previous_camera_chassis = self.camera_msg.camera_chassis
        self.previous_camera_main_navigation = self.camera_msg.camera_main_navigation

    def __set_previous_jetson_values(self):
        self.previous_jetson_cpu = self.jetson_msg.jetson_cpu
        self.previous_jetson_ram = self.jetson_msg.jetson_ram
        self.previous_jetson_emmc = self.jetson_msg.jetson_emmc
        self.previous_jetson_nvme_ssd = self.jetson_msg.jetson_nvme_ssd
        self.previous_jetson_gpu_temp = self.jetson_msg.jetson_gpu_temp

    def __set_previous_frsky_value(self):
        self.previous_frsky_controller_connection_status = self.FrSky_msg.frsky_controller_connection_status

    def __set_previous_wheel_values(self):
        self.previous_wheel_front_left = self.wheel_msg.front_left
        self.previous_wheel_middle_left = self.wheel_msg.middle_left
        self.previous_wheel_rear_left = self.wheel_msg.rear_left
        self.previous_wheel_front_right = self.wheel_msg.front_right
        self.previous_wheel_middle_right = self.wheel_msg.middle_right
        self.previous_wheel_rear_right = self.wheel_msg.rear_right

    def __set_previous_gps_values(self):
        self.previous_gps_connected = self.GPS_msg.gps_connected
        self.previous_gps_fix = self.GPS_msg.gps_fix
        self.previous_gps_num_satellites = self.GPS_msg.num_satellites
        self.previous_gps_horizontal_dilution = self.GPS_msg.horizontal_dilution
        self.previous_gps_kmph = self.GPS_msg.kmph
        self.previous_gps_heading = self.GPS_msg.gps_heading

    def __set_previous_misc_values(self):
        self.previous_arm_connection_status = self.misc_msg.arm_connection_status
        self.previous_arm_end_effector_connection_statuses = self.misc_msg.arm_end_effector_connection_statuses
        self.previous_chassis_pan_tilt_connection_status = self.misc_msg.chassis_pan_tilt_connection_status
        self.previous_sample_containment_connection_status = self.misc_msg.sample_containment_connection_status
        self.previous_tower_connection_status = self.misc_msg.tower_connection_status

    def __set_previous_battery_values(self):
        self.previous_battery_voltage = self.battery_message.battery_voltage

    def on_update_requested(self,  _):
        self.manual_update_requested = True

    def main_loop(self):
        # Update all message values
        self.__pull_new_message_values()

        if (self.battery_message.battery_voltage != self.previous_battery_voltage or
                self.manual_update_requested):
            if (time() - self.last_iris_message_sent) > (1.0 / MAX_IRIS_UPDATE_HERTZ):
                self.__set_previous_battery_values()
                self.pub_battery.publish(self.battery_message)
                self.last_iris_message_sent = time()

        # Camera Check -- if current value is now different from previous value,
        # update the previous value for cameras and publish to listening Subscribers
        if (self.camera_msg.camera_zed != self.previous_camera_zed or
                self.camera_msg.camera_undercarriage != self.previous_camera_undercarriage or
                self.camera_msg.camera_chassis != self.previous_camera_chassis or
                self.camera_msg.camera_main_navigation != self.previous_camera_main_navigation or
                self.manual_update_requested):
            self.__set_previous_camera_values()
            self.pub_camera.publish(self.camera_msg)

        # Placeholder Jetson Info Check
        if (self.jetson_msg.jetson_cpu != self.previous_jetson_cpu or
                self.jetson_msg.jetson_ram != self.previous_jetson_ram or
                self.jetson_msg.jetson_emmc != self.previous_jetson_emmc or
                self.jetson_msg.jetson_nvme_ssd != self.previous_jetson_nvme_ssd or
                self.jetson_msg.jetson_gpu_temp != self.previous_jetson_gpu_temp or
                self.manual_update_requested):
            if (time() - self.last_jetson_message_sent) > (1.0 / MAX_JETSON_UPDATE_HERTZ):
                self.__set_previous_jetson_values()
                self.pub_jetson.publish(self.jetson_msg)
                self.last_jetson_message_sent = time()

        # Placeholder FrSky Controller Check
        if (self.FrSky_msg.frsky_controller_connection_status != self.previous_frsky_controller_connection_status or 
                self.manual_update_requested):
            self.__set_previous_frsky_value()
            self.pub_FrSky.publish(self.FrSky_msg)

        # bogie wheel status check
        if (self.wheel_msg.front_left != self.previous_wheel_front_left or
                self.wheel_msg.middle_left != self.previous_wheel_middle_left or
                self.wheel_msg.rear_left != self.previous_wheel_rear_left or
                self.wheel_msg.front_right != self.previous_wheel_front_right or
                self.wheel_msg.middle_right != self.previous_wheel_middle_right or
                self.wheel_msg.rear_right != self.previous_wheel_rear_right  or
                self.manual_update_requested):
            self.__set_previous_wheel_values()
            self.pub_wheel.publish(self.wheel_msg)

        # Placeholder GPS Information check
        # if (self.GPS_msg.UTC_GPS_time != self.previous_UTC_GPS_time or
        #         self.GPS_msg.UTC_GPS_time != self.previous_GPS_connection_status or
        #         self.manual_update_requested):
        #     self.__set_previous_gps_values()
        #     self.pub_GPS.publish(self.GPS_msg)

        # GPS info status -- connected, fix, satellites, horizontal dilution, kmph, and heading
        if (self.GPS_msg.gps_connected != self.previous_gps_connected or
                self.GPS_msg.gps_fix != self.previous_gps_fix or
                self.GPS_msg.num_satellites != self.previous_gps_num_satellites or
                self.GPS_msg.horizontal_dilution != self.previous_gps_horizontal_dilution or
                self.GPS_msg.kmph != self.previous_gps_kmph or
                self.GPS_msg.gps_heading != self.previous_gps_heading):
            self.__set_previous_gps_values()
            self.pub_GPS.publish(self.GPS_msg)

        # Placeholder Misc Information check
        if (self.misc_msg.arm_connection_status !=
                self.previous_arm_connection_status or
                self.misc_msg.arm_end_effector_connection_statuses !=
                self.previous_arm_end_effector_connection_statuses or
                self.misc_msg.chassis_pan_tilt_connection_status !=
                self.previous_chassis_pan_tilt_connection_status or
                self.misc_msg.sample_containment_connection_status !=
                self.previous_sample_containment_connection_status or
                self.misc_msg.tower_connection_status != self.previous_tower_connection_status or
                self.manual_update_requested):
            self.__set_previous_misc_values()
            self.pub_Misc.publish(self.misc_msg)

        if self.manual_update_requested:
            self.manual_update_requested = False


def main(args=None):
    rclpy.init(args=args)
    system_statuses = SystemStatuses()
    rclpy.spin(system_statuses)
    system_statuses.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
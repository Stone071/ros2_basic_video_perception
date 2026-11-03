# This file will publish frames from a pre-recorded video to ROS2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy, LivelinessPolicy
from rclpy.qos import qos_profile_sensor_data
from rclpy.duration import Duration
from rclpy.event_handler import PublisherEventCallbacks
from sensor_msgs.msg import Image
import numpy as np
import cv2

# GLOBALS
VIDEO_PATH = "video-data/00477198-d980-4010-be20-097f2acb5bdf.mp4_00477198-d980-4010-be20-097f2acb5bdf.mp4"

class VideoPublisherNode(Node):
    """
    VideoPublisherNode objects read in a video frame by frame and publish each frame
    to the "video_stream" topic. The publishing period is determined by the fps of the
    video file.
    """
    ### MEMBERS ###
    # All VideoPublisherNode nodes will publish to topic "video_stream", and use the same QoS
    topic = "video_stream"
    
    # Any data for which we desire real-time performance should prefer BEST_EFFORT publishing
    # over RELIABLE publishing, reducing latency of published messages
    publish_deadline = Duration(nanoseconds=50000000) # 50ms
    message_lifespan = Duration(nanoseconds=100000000) # 100ms
    lease_duration = Duration(nanoseconds=200000000) # 200ms
    publish_queue_depth = 5
    video_streamer_qos = QoSProfile(
            history=HistoryPolicy.KEEP_ALL,
            depth=publish_queue_depth, # reduce overhead by maintaining few past samples
            reliability=ReliabilityPolicy.BEST_EFFORT, # prefer low latency to absolute reliability
            durability=DurabilityPolicy.VOLATILE, # DO NOT send old samples to late-joining subs
            deadline=publish_deadline, # 50ms period is 20 fps
            lifespan=message_lifespan, # 100ms lifespan of message on topic
            liveliness=LivelinessPolicy.MANUAL_BY_TOPIC, # must publish to be considered alive
            liveliness_lease_duration=lease_duration # 200ms of no publish before considered dead
        )

    ### METHODS ###
    def __init__(self):
        # Call Node class init func
        super().__init__("video_publisher_node")
        
        # Temp timing
        self.last_report_time = None
        self.publish_count = 0

        # Set up video capture
        self.feed = VIDEO_PATH
        self.cap = cv2.VideoCapture(self.feed)
        self.this_frame = None
        self.next_frame = None

        # Set to receive a callback when publisher misses deadline
        publisher_event_callbacks = PublisherEventCallbacks(
            deadline=self._deadline_missed_callback, # called when publishing deadline is missed
            liveliness=self._liveliness_missed_callback, # called when publisher misses liveliness duration
            matched=self._subscriber_matched_callback, # called when a subscriber joins topic
            incompatible_qos=self._incompatible_qos_callback, # called when QoS mismatch on topic
            use_default_callbacks=True
        )

        # Init the publisher
        self.publisher = self.create_publisher(
            Image,                               # message type
            VideoPublisherNode.topic,            # topic to publish to 
            VideoPublisherNode.video_streamer_qos, # qos prefer real-time performance
            #10,
            #qos_profile_sensor_data,
            event_callbacks=publisher_event_callbacks # hand callbacks to publisher
        )

        # Check for set up errors
        if (not self.cap.isOpened()):
            self.get_logger().error(f"Could not open video file: {self.feed}!")
            cleanup_and_exit([self])
            exit()

        # Init publish timer
        self.timer = self.create_timer(
            (1.0 / self.cap.get(cv2.CAP_PROP_FPS)), # period, units of seconds
            #0.33, # 330ms period
            self._publish_frame # timer calls this callback
        )

        # VideoPublisherNode ready
        self.get_logger().info(f"{self.get_name()} ready")

    # Name as a "private" method
    def _incompatible_qos_callback(self, info):
        self.get_logger().warn(f"QoS mismatch on" \
            f'"{VideoPublisherNode.topic}"')

    # Name as a "private" method
    def _subscriber_matched_callback(self, info):
        self.get_logger().info(f"There are now {info.current_count} matched subscribers on" \
            f'"{VideoPublisherNode.topic}"')

    # Name as a "private" method
    def _deadline_missed_callback(self, info):
        self.get_logger().warn(f"{self.get_name()} missed publish deadline: " \
            f"{VideoPublisherNode.publish_deadline}\n" \
            f"total: {info.total_count}\nchanged: {info.total_count_change}")
    
    # Name as a "private" method
    def _liveliness_missed_callback(self, info):
        self.get_logger().warn(f"{self.get_name()} missed liveliness deadline: " \
            f"{VideoPublisherNode.lease_duration}\n" \
            f"total: {info.total_count}\nchanged: {info.total_count_change}")

    # Name as "private" method
    def _publish_frame(self):
        # Temp timing check
        self.publish_count += 1
        if self.publish_count % 100 == 0:
            now = self.get_clock().now()
            if self.last_report_time is not None:
                elapsed = (now - self.last_report_time).nanoseconds / 1e9
                rate = 100 / elapsed
                self.get_logger().info(f"Pub'ing at {rate:.2f} Hz")
            self.last_report_time = now

        # Check if we have a frame ready
        if (self.next_frame is not None):
            self.this_frame = self.next_frame
        else:
            success, self.this_frame = self.cap.read()
            if (not success):
                # the video probably ended
                self._seek_video_beginning()
                success, self.this_frame = self.cap.read()

        # Reset next frame
        self.next_frame = None

        # Pack the frame into an Image message
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera"
        #uint32 height
        #uint32 width
        #string encoding
        #uint8 is_bigendian
        #uint32 step
        #uint8[] data
        msg.height = self.this_frame.shape[0] # height is m, number of rows
        msg.width = self.this_frame.shape[1] # width is n, number of cols
        msg.encoding = "bgr8"
        msg.is_bigendian = False
        msg.step = self.this_frame.strides[0] # number of bytes to skip to get to next row
        msg.data = self.this_frame.tobytes()
        self.publisher.publish(msg)

        # Output some image metrics. Different for each video.
        # Useful when inspecting topic bandwidth using `ros2 topic bw`
        self.get_logger().info(f"Published frame\nDims: {msg.width}x{msg.height}\n" \
                f"Encoding: {msg.encoding}\n# Bytes: {len(msg.data)}", once=True)

        # Prepare the next frame as soon as the previous is published.
        success, self.next_frame = self.cap.read()
        if (not success):
            self._seek_video_beginning()
            success, self.next_frame = self.cap.read()

        # Perception node is going to resize to 640x640 anyway, just do that work here
        self.next_frame = cv2.resize(self.next_frame, (640,640))

    # Name as "private"
    def _seek_video_beginning(self):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.get_logger().info("Video beginning again...")

    # Override destroy to cleanup video file
    def destroy_node(self):
        self.get_logger().info(f"Cleaning {self.get_name()} resources...")
        
        # Try to release the video resource
        try:
            self.cap.release()
            self.get_logger().info(f"Released resource at {self.feed}")
        except Exception as e:
            self.get_logger().error(f"Error during cleanup: {e}")
            
        # Call the Node class's destroy_node()
        super().destroy_node()


### FILE FUNCS ###
def main():
    """
    Main entry for ROS
    """
    # Init rclpy
    rclpy.init()

    # Instantiate our publisher node
    node = VideoPublisherNode()
    
    # Spin the node
    rclpy.spin(node)

    # Cleanup
    cleanup_and_exit([node])

def cleanup_and_exit(nodesToClean: list):
    """
    Clean up any active nodes and cleanup rclpy
    """
    for node in nodesToClean:
        node.get_logger().info(f'Destroying node "{node.get_name()}"...')
        node.destroy_node()
    rclpy.shutdown()

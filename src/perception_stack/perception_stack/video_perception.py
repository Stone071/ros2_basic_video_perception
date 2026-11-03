# Here we will receive images, queue them, and run inference on them when pulled out of the queue.
# This is like any RTOS code. Decouple message reception from processing.

# IMPORTS
import threading
import queue
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy, LivelinessPolicy
from rclpy.qos import qos_profile_sensor_data
from rclpy.event_handler import SubscriptionEventCallbacks
from sensor_msgs.msg import Image
from ultralytics import YOLO
import onnxruntime as ort
import cv2
import numpy as np
from supervision import Detections
from trackers import ByteTrackTracker

### GLOBALS ###
CONF_THRESH = 0.45
SESSION = ort.InferenceSession(
    "models/yolo11n.onnx",
    providers=["CUDAExecutionProvider","CPUExecutionProvider"]
)

### CLASS DEFS ###
class VideoPerceptionNode(Node):
    """
    VideoPerceptionNode will operate on video frames to perform all useful perception functions.
    This flow is intended:
    1. Run inference on the frame
    2. Perform object tracking on the detected results
    3. Validate detections by waiting for tracked objects to reach a certain age
    4. Determine movement of objects relative to the camera

    Logged Output:
    * The perception node will track the processing time for each frame and log if it is falling behind realtime.
    * The perception node will log if the perception queue becomes full.
    """
    ### MEMBERS ###
    topic = "video_stream"
    
    # Any data for which we desire real-time performance should prefer BEST_EFFORT publishing
    # over RELIABLE publishing, reducing latency of published messages
    receive_deadline = Duration(nanoseconds=70000000) # 70ms, must be > publisher deadline
    message_lifespan = Duration(nanoseconds=100000000) # 100ms
    lease_duration = Duration(nanoseconds=200000000) # 200ms
    receive_queue_depth = 5
    video_receiver_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=receive_queue_depth, # reduce overhead by maintaining few past samples
            reliability=ReliabilityPolicy.BEST_EFFORT, # prefer low latency to absolute reliability
            durability=DurabilityPolicy.VOLATILE, # DO NOT send old samples to late-joining subs
            deadline=receive_deadline, # 50ms period is 20 fps
            lifespan=message_lifespan, # 100ms lifespan of message on topic
            liveliness=LivelinessPolicy.MANUAL_BY_TOPIC, # must publish to be considered alive
            liveliness_lease_duration=lease_duration # 200ms of no publish before considered dead
        )

    ### METHODS ###
    def __init__(self):
        # Call init for Node class
        super().__init__("video_perception_node")
        
        # Load Yolo11 nano
        self.model = YOLO("models/yolo11n.pt")

        # Receive callbacks when there are QoS issues
        subscriber_event_callbacks = SubscriptionEventCallbacks(
            deadline=self._deadline_missed_callback, # called when topic misses deadline
            liveliness=self._liveliness_missed_callback, # called when publisher liveliness changes
            message_lost=self._message_lost_callback, # called when a message is lost
            matched=self._publisher_matched_callback, # called when publisher joins topic
            incompatible_qos=self._qos_mismatch_callback, # called when QoS mismatch on topic
            use_default_callbacks=True
        )

        # Subscribe to topic
        self.subscription = self.create_subscription(
            Image,                     # message type
            VideoPerceptionNode.topic, # subbed topic
            self._image_callback,       # callback for each message
            VideoPerceptionNode.video_receiver_qos, # QoS preferring real-time to reliable
            #10,
            #qos_profile_sensor_data,
            event_callbacks=subscriber_event_callbacks # register our callbacks
        )

        # Place frames for perception into a bounded queue.
        # Frames will drop if queue is full
        self.frame_queue = queue.Queue(maxsize=5)

        # Start a thread which runs the inference
        self.inference_thread = threading.Thread(
            target=self._run_inference, # inference runs constantly in a separate thread
            daemon=True # daemon threads will exit if they are the only tasks active
        )
        self.inference_thread.start()

        # Init complete
        self.get_logger().info(f"{self.get_name()} node ready")

    ### METHODS ###
    # Name as "private"
    def _message_lost_callback(self, info):
        self.get_logger().info(f'A message was lost on topic "{VideoPerceptionNode.topic}"\n'\
        f"Count: {info.total_count}")

    # Name as "private"
    def _publisher_matched_callback(self, info):
        self.get_logger().info(f"There are now {info.current_count} matched publishers on" \
            f'"{VideoPerceptionNode.topic}"')

    # Name as "private"
    def _qos_mismatch_callback(self, info):
        self.get_logger().error(f'{self.get_name()} unable to subscribe to topic ' \
            f'"{VideoPerceptionNode.topic}" due to QoS mismatch!\n'
            f"Info: {info}")

    # Name as "private"
    def _deadline_missed_callback(self, info):
        self.get_logger().warn(f"{self.get_name()} missed frame reception deadline: " \
            f"{VideoPerceptionNode.receive_deadline}\n" \
            f"total: {info.total_count}\nchanged: {info.total_count_change}")

    # Name as a "private" method
    def _liveliness_missed_callback(self, info):
        self.get_logger().warn(f'A publisher on topic "{VideoPerceptionNode.topic}" had a change in liveliness\n' \
            f"Alive Count: {info.alive_count}\n" \
            f"Not Alive Count: {info.not_alive_count}")

    # Name as "private"
    def _image_callback(self, msg):
        # Drop the frame if inference is not keeping up.
        # Never want to block the callback thread.
        if not self.frame_queue.full():
            self.frame_queue.put(msg)
        else:
            self.get_logger().warn(f"{self.get_name()} perception queue is full!")

    # Name as "private"
    def _run_inference(self):
        while rclpy.ok():
            # Get a message
            msg = self.frame_queue.get()

            # Mark time
            t0 = self.get_clock().now()

            # Convert img msg to cv2
            frame = img_msg_to_cv2(msg)

            # Run inference
            #results = self.model(frame, conf=CONF_THRESH, verbose=False)
            results = run_onnx_inference(frame)
            
            # Check inference time
            deltaT = self.get_clock().now() - t0
            if (deltaT.nanoseconds > 33000000): # UPDATE THIS TO BE BASED ON FRAME RATE
                self.get_logger().warn(f"Inference took {deltaT}, falling behind real time.")
            else:
                self.get_logger().info(f"Inference took {deltaT}")

            #detections = results[0].boxes
            #self.get_logger().info(f"Detected {len(detections)} objects above threshold {CONF_THRESH}")

class RoboticsTracker:
    ### METHODS ###
    def __init__(self):
        # track buffer controls how long a track
        # survives without a matching detection.
        self.tracker = ByteTracker(
            track_thresh=0.45,
            match_thresh=0.8,
            track_buffer=30,
            frame_rate=30,
        )

    def update(self, yolo_results, frame_shape):
        # Since we feed one frame at a time, there is one result object in results
        boxes = yolo_results[0].boxes

        if len(boxes) == 0:
            return []

        # Get a numpy array of the detected bounding boxes and metadata
        xyxy = boxes.xyxy.cpu().numpy()
        confidence = boxes.conf.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)

        # Make a detections object
        detections = Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_ids
        )

        # Feed the detections object to the tracker
        tracked = self.tracker.update(
            detections=detections,
            frame_resolution_wh=(frame_shape[1], frame_shape[0])
        )

        # tracked.tracker_id gives each detection a stable integer ID
        # that persists across frames as long as the track is alive.
        return tracked


### GLOBALS ###
CONF_THRESH = 0.45
MIN_TRACK_AGE = 3      # frames a track must exist before being trusted
JITTER_THRESH = 2.0 # maximum acceptable platform acceleration


### FILE FUNCS ###
def is_actionable_detection(detection, track_age: int, platform_acceleration: float):
    """
    Cross check each detection with its age and any platform acceleration before trusting it
    Returns True only when all three
    1. Model confidence above threshold
    2. Track has existed long enough to not be noise
    3. Platform carrying the sensor is not vibrating or accelerating
       sharply enough to corrupt the sensor data
    """
    if detection.confidence < CONF_THRESH:
        return False, "low_confidence"

    if track_age < MIN_TRACK_AGE:
        return False, "track_not_stabilized"

    if platform_acceleration > JITTER_THRESH:
        return False, "platform_unstable"

    return True, "actionable"

def img_msg_to_cv2(msg: Image) -> np.ndarray:
    channels_by_encoding = {
        "mono8": 1,
        "rgb8": 3,
        "bgr8": 3,
        "rgba8": 4,
        "bgra8": 4
    }
    channels = channels_by_encoding[msg.encoding]
    row = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    width_in_bytes = msg.width * channels
    image = row[:, :width_in_bytes].reshape(msg.height, msg.width, channels)
    return image

def run_onnx_inference(frame: np.ndarray):
    # Preprocess: resize, normalize, add batch dimensions, convert to float32
    if (np.shape(frame) != (640,640)):
        img = cv2.resize(frame, (640,640))
    img = img.astype(np.float32) / 255.0
    img = img.transpose(2, 0, 1)      # HWC to CHW
    img = np.expand_dims(img, axis=0) # add batch dimension

    outputs = SESSION.run(None, {"images": img})
    return outputs

def main():
    rclpy.init()
    node = VideoPerceptionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

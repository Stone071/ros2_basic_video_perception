# ROS2 Camera Feed and Video Inference

This project encompasses building a couple of nodes for ROS2 in Python, using various ROS tools for debug and inspection, and properly configuring a virtual machine linux environment for ROS2 development.

## Purpose

This is my initial attempt at building a project with ROS, with the intent of learning the basics.

## Key Takeaways

ROS appears to provide services through API calls to achieve most functions/requirements which I am familiar with from my work in real-time embedded systems, and ROS2 improves on ROS1 by providing more customizable topics that can be tailored toward reliability or data throughput.

Some of the tasks ROS makes really easy that are important in large real-time systems:

* Asynchronous communication
* Easy queue creation and thread-safe access
* Easy timing calculations
* Deadline setting
* Peer discovery

## Architecture

This project is composed of two nodes communicating through a single topic. The first node reads in a video file using OpenCV2 and publishes individual frames onto the topic at the frame rate of the video. This is approximately the same as what would be happening in a live system with a camera feed.

The second node subscribes to the topic and receives each frame, placing the frame into its own internal queue to be consumed for inference performed by ONNX runtime, which is running the YOLOv11 computer vision model converted to .onnx format.

The inference node identifies objects in the frame and tracks their movement across frames.

![Project Architecture Diagram](ros2-basic-video-perception-architecture.png)

## Linux/Middleware Environment Customizations

### Issue

* Complications getting large Image messages to transfer through the DDS middleware.

### Diagnosis and Solution

```bash
# This command sets up FASTDDS for large data with 10MB sockets. Our 1080p frames are about 6MB, so there is healthy margin here with 10MB.
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTDDS_BUILTIN_TRANSPORTS='LARGE_DATA?max_msg_size=10MB&sockets_size=10MB'

# Starting the nodes after setting this produced error messages that the socket size was not able to be set. The linux socket size was upped to 16MB to fix.
sudo sysctl -w net.core.rmem_max=16777216
sudo sysctl -w net.core.wmem_max=16777216
```

There was an interesting issue when using the video-stream topic to publish and consume relatively large Image frames. When using Reliable Quality of Service on the video-stream topic, Image messages were published and received by subscribers as normal. However, given the real-time nature of the task being live video processing and inference, a Reliable QoS is not desired, as it results in longer transmit times due to messages being retried in the case of failure.

As soon as the QoS reliability policy was changed to Best Effort, the subscriber began receiving little to no data. `ros2 topic bw` and `ros2 topic hz` occasionally did show that data was appearing on the topic, but very little, and far less/far less frequently than reported by the publisher.

After setting up callbacks for events occurring on the topic, it was clear that every Image message published by the publisher was "Lost" in transit when using FastDDS as the ROS middleware. CycloneDDS was also tried, and in this case there was no data received on the bus, and no callbacks reported for lost messages. However, if the frames were resized to 320x240 before publishing on the topic as Image messages, all data was received as expected. It was found that the middleware and Linux environment were not configured to handle the large payloads being published as single messages. A single 1920x1080 frame with 3 byes of color information is a data payload of at least 5.9 MB.

To resolve this issue, some middleware/linux customizing was required. FastDDS has a "Large Data" mode which allows the user to specify a maximum message size and socket size. This will increase the size of individual messages which can be sent, and reduce the number of message fragments which need to be sent over the network to encapsulate an individual Image message.

Increasing the FastDDS settings beyond what the Linux Kernel is set up for will produce error messages on startup, and not resolve the issue, so the Linux Kernel socket size also has to be increased. The sysctl commands listed increase the maximum buffer available for reading and writing on all sockets, including the TCP and UDP sockets used by the ROS middleware.

## Notes on Quality of Service

It seems to me like customizable Quality of Service is one of the primary improvements of using ROS2 over ROS1. I can't imagine trying to develop a real-time deterministic system without the controls exhibited here, and I spent a bit of time understanding the options available. Each time I wondered if there was a control or measurement for X, I found one in QoS or event callbacks.

For my "video-stream" topic, I made use of the following controls.

```python
    # Any data for which we desire real-time performance should prefer BEST_EFFORT publishing
    # over RELIABLE publishing, reducing latency of published messages
    publish_deadline = Duration(nanoseconds=50000000) # 50ms deadline. 25 fps is 40ms period.
    message_lifespan = Duration(nanoseconds=50000000) # 50ms persistence of each message on topic.
    lease_duration = Duration(nanoseconds=500000000) # Publisher is considered dead after 500ms without publishing.
    publish_queue_depth = 5
    video_streamer_qos = QoSProfile(
            history=HistoryPolicy.KEEP_ALL,
            depth=publish_queue_depth, # reduce overhead by maintaining few past samples
            reliability=ReliabilityPolicy.BEST_EFFORT, # prefer low latency to absolute reliability
            durability=DurabilityPolicy.VOLATILE, # DO NOT send old samples to late-joining subs
            deadline=publish_deadline, # 50ms gives 25% margin on 40ms period before throwing a warning.
            lifespan=message_lifespan, # Don't let old images persist on topic. Just use the new ones.
            liveliness=LivelinessPolicy.MANUAL_BY_TOPIC, # must publish to be considered alive
            liveliness_lease_duration=lease_duration # 500ms of no publish before considered dead
        )
```

On my development virtual machine, I use different values for each duration, since the VM ultimately cannot keep up with real-time 1080p video inference.

```python
        # Set to receive a callback when publisher misses deadline
        publisher_event_callbacks = PublisherEventCallbacks(
            deadline=self._deadline_missed_callback, # called when publishing deadline is missed
            liveliness=self._liveliness_missed_callback, # called when publisher misses liveliness duration
            matched=self._subscriber_matched_callback, # called when a subscriber joins topic
            incompatible_qos=self._incompatible_qos_callback, # called when QoS mismatch on topic
            use_default_callbacks=True
        )
```

The quality of service object and event callbacks object are both passed as arguments when creating a publisher or subscriber object for a topic. There are slightly different options available for event callbacks as a publisher or subscriber.

## Development Architecture

Developed in a virtual machine using ROS2 jazzy and a python virtual environment.

### Issues

* Matching ROS version, system python version, and libraries available for this python version.

In my experience, developing complex projects in Python which knit together several large libraries can introduce a dependency chain that is out of the developer's control at at times becomes difficult to maintain. I'm sure part of the challenge here is my own lack of experience developing in this fashion, but I did find myself facing this problem once again developing this project.

The specific issue I faced was that I first decided to develop this project directly on my personal computer, running Ubuntu 26.04 and Python 3.14.14. Since ROS2 releases target specific Linux and Python versions, I chose ROS2 Lyrical Luth, the release of ROS2 compatible with my OS and system Python, which is also the latest LTS release. This choice would prove to be incompatible with the other major dependency in the original version of this project, which was the CARLA Simulator. CARLA was going to be used as a source of simulated objects and a camera feed, but the Python module is only available for Python 3.12 at the latest. While it is possible to build Python modules from source for the system Python in use, I would hesitate to pursue this option, as these custom builds have not been verified. 

### Solution

The solution here is the option I should've pursued from the start, which is to use a virtual machine as the development environment. This option puts the developer in control of the Linux version, system Python version, and makes it easy to track exactly what dependencies have been installed in development and are necessary for runtime. Since the development/functional testing environment and deployment environment must match, and it does not make sense to develop directly on the deployment machine, the logical choice is to control the development environment in this way.

It is fortunate also that ROS2 is compatible with developing in a virtual Python environment. Though ROS2 runs using the system Python interpreter, other Python dependencies can be installed in a Python development environment using venv. So ultimately, development for this project was performed in an Ubuntu 24.04 virtual machine using ROS2 Jazzy Jalisco, and all other Python modules installed into a virtual Python environment using venv.

## Tools used

```
colcon build --symlink-install
ros2 topic hz
ros2 topic bw
```

As a first time developer using ROS, these three tools were used over and over. The `--symlink-install` argument for colcon made all the executables symlinked to the development source code, so the project did not have to be rebuilt anytime changes were made that I wanted to test.

`ros2 topic hz` and `ros2 topic bw` were very useful for getting a verified view of data being transferred on a topic. `hz` validated the frequency of messages, and `bw` validated the rate of data appearing over the topic, which is another important metric for large data payloads like Image messages.

## Modules Used

- ROS2
- Ultralytics YOLOv11
- ~~ONNX ort~~
- OpenVINO
- OpenCV2
- ~~Roboflow Supervision~~
- ~~Roboflow Trackers~~

ROS2 is the backbone of the project here, handling major tasks such as timing, node creation, data transfer between nodes, data quality tracking.

YOLOv11 is the computer vision model being used to infer the identity of objects in a frame.

ONNX runtime (ort) is an engine designed to assist in deployment of machine learning models on different hardware and software stacks. When developing on one machine and deploying on another, adapting the machine learning model to the hardware it will be deployed on is a critical step. This is especially true when deploying to mobile robotic hardware, which may not posess as much compute as the development machine.

Ultimately, I ended up using OpenVINO to deploy the YOLOv11 model, since OpenVINO is optimized for Intel CPUs. I was not able to realize much speed benefit from this change though. For a true deployment of this system, more quantitative benchmarking of different model deployments and hardware would be necessary.

OpenCV2 is a long standing set of tools developed for performing computer vision tasks in Python. In this project, it is mostly used as as a method to easily read video files. Under the hood, CV2 represents most data objects as Numpy NDArrays, which is an extremely common standard for working with multi-demensional matrix data in Python.

Supervision and Trackers are used together to perform object detection and tracking which persists across consecutive frames of a video. Inference allows us to detect what is in a still image from a video, and object detection/tracking allows us to assign unique identities to each object and make observations of them over time. I ultimately did not implement the object tracking, as my laptop was already struggling to complete the inference step in a reasonable timeframe.

All of these Python modules except OpenCV2 are new to me, and I enjoyed learning a bit about each. They each present highly useful tools for computer vision tasks which I hope to make use of in future projects.

## Additional Notes

Developing real-time systems in Python is an interesting change for me. To be honest, I like how a compiled language catches most issues before runtime. With Python, I found that I was making trivial mistakes in uncommonly called code paths, and only finding bugs during unlikely testing scenarios. This made clear how important a static checker/linter and thorough unit testing is for Python programs that need to be robust.

## What I learned

- Setting up a ROS2 Python package
- Basic ROS tools
    - ros2 topic list -t
    - ros2 topic hz
    - ros2 topic bw
    - ros2 service list -t
    - ros2 interface show
    - `$dir(rclpy)` where documentation is lacking
- ROS2 Quality of Service Controls
- Basics of using computer vision models in Python
- Debugging and configuring Linux/RMW for transmitting large messages
- Sourcing datasets from HuggingFace

I am actually not going to use carla, since I cannot fit the simulator on my machine. I will download some datasets from huggingface. I will start with [this](https://huggingface.co/datasets/HumynLabs/Street-videos) one.

Alright what I ended up doing is using the install script to install the hf tool and then using the hf download command. This seems to have sourced the data correctly and now opencv is able to open video.

`hf download HumynLabs/Street-videos --repo-type=dataset`
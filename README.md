# README

In this directory I will follow this tutorial to learn some ROS2 and object detection

[Tutorial on FreeCodeCamp](https://www.freecodecamp.org/news/how-to-build-a-real-time-object-detection-and-tracking-pipeline-with-ros-2-and-yolov11/#heading-prerequisites)

I am also going to use a virtual python environment, because I think I will be installing a lot of new tools. This environment will be in .venv

Here's all the steps that the freecodecamp tutorial does not cover:

1. Only create the perception_stack/src folder, then run the ros2 pkg create command. Do not create any subdirectories or python files first.
2. To use ROS2 run to execute the executable parts of your ROS2 package, you need to declare the executables in your package to ROS. This is done in the package.xml and is demonstrated [here](https://docs.ros.org/en/foxy/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Publisher-And-Subscriber.html)
3. ROS and Python version management can become complicated when knitting together many python packages. I upgraded to Ubuntu 26.04 to get the latest ROS install, but then my python interpreter upgraded to 3.14, and many python packages are not available for 3.14.
4. This is all solved by running ROS2 in a virtual machine which is Ubuntu 24.04, with Python 3.12 as the system python.


Python Packages:
* numpy
* carla
* colcon-common-extensions

I am actually not going to use carla, since I cannot fit the simulator on my machine. I will download some datasets from huggingface. I will start with [this](https://huggingface.co/datasets/HumynLabs/Street-videos) one.

Alright what I ended up doing is using the install script to install the hf tool and then using the hf download command. This seems to have sourced the data correctly and now opencv is able to open video.

`hf download HumynLabs/Street-videos --repo-type=dataset`

I need to learn a bit about these image classification models I am using.

Ultralytics YOLOv11 first:

* Ultralytics YOLO models return a list of Results objects or a generator of objects when keyword arg stream=True is passed
* Results objects seem to have members 
    * .boxes -> Boxes object for bounding box 
    * .masks -> Masks object for segmentation masks
    * .keypoints -> Keypoints object for pose detection
    * .probs -> Probs object for classification outputs
    * .obb -> Oriented boxes object for OBB
    * .show() method to display on screen
    * .save(filename='x.jpg') method
    * all members and methods seem to be shown on [this](https://docs.ultralytics.com/modes/predict)) 
* There's actually some timing members built right into the result

Okay I've tried several different QoS profiles including my own, qos_profile_sensor_data, and 10.
On each of them, messages are getting lost. The publishing is fine, but messages are getting lost. I think it is due to the CPU not keeping up. What if I 

* manually publish at a slower rate, 
* or publish lower resolution video?

Okay Copilot helped me identify that the middleware was not handling large messages. After resizing the frames to 320x240, they came through perfectly.
To get the 1080p frames to come through, FASTDDS had to be configured to large messages, and linux socket sizes had to be adjusted to allow this.

This command sets up FASTDDS for large data with 10MB sockets. Our 1080p frames are about 6MB, so there is healthy margin here with 10MB.
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTDDS_BUILTIN_TRANSPORTS='LARGE_DATA?max_msg_size=10MB&sockets_size=10MB'

Starting the nodes after setting this produced error messages that the socket size was not able to be set. We adjusted the linux socket size to 16MB
sudo sysctl -w net.core.rmem_max=16777216
sudo sysctl -w net.core.wmem_max=16777216

Now we no longer have lost messages on the topic. But did we need to do this? Am I resource constrained enough that I should be passing in smaller images anyway

Alright cool, I have my custom QoS running on both nodes, publishing at video frame rate at full resolution. All messages are being received. My perception node can't keep up though. Inference is taking about 200ms per frame. So I should either shrink the frames or slow down the video... Well, turns out YOLOv11 runs at 640x640 anyway. Having the publisher publish at this resolution did not speed up inference at all. Maybe ONNX will be faster?

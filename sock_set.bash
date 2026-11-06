#!/bin/bash

# This command sets up FASTDDS for large data with 10MB sockets. Our 1080p frames are about 6MB, so there is healthy margin here with 10MB.
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTDDS_BUILTIN_TRANSPORTS='LARGE_DATA?max_msg_size=10MB&sockets_size=10MB'
echo $RMW_IMPLEMENTATION
echo $FASTDDS_BUILTIN_TRANSPORTS

# Starting the nodes after setting this produced error messages that the socket size was not able to be set. We adjusted the linux socket size to 16MB
sudo sysctl -w net.core.rmem_max=16777216
sudo sysctl -w net.core.wmem_max=16777216

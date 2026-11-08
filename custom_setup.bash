#!/bin/bash

ros2_path="/opt/ros/jazzy/setup.bash"
python_venv_path=".venv/bin/activate"
sock_set_path="sock_set.bash"
install_setup_path="install/setup.bash"

echo "Sourcing $ros2_path"
source $ros2_path

echo "Sourcing $python_venv_path"
source $python_venv_path

echo "Sourcing $sock_set_path"
source $sock_set_path

echo "Sourcing $install_setup_path"
source $install_setup_path


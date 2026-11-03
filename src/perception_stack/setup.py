from setuptools import find_packages, setup

package_name = 'perception_stack'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Zachary Stone',
    maintainer_email='zachary.stone15@gmail.com',
    description='Learning about object detection and ROS package creation.',
    license='Apache License 2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'video_publisher = perception_stack.video_publisher:main',
            'video_perception = perception_stack.video_perception:main',
        ],
    },
)

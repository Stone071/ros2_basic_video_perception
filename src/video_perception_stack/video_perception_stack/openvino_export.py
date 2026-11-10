from ultralytics import YOLO

# Load a YOLO26 model
model = YOLO("models/yolo11n.pt")

# Export the model to OpenVINO format
model.export(
    format="openvino",
    imgsz=640,
    dynamic=False, # non dynamic batch size
    simplify=True,
    batch=1, # we are always processing images one at a time
)


from ultralytics import YOLO

def export_perception_model(input_model: str):
    """
    Exports a YOLOv11 model to ONNX format for edge deployment.

    The dynamic_axes setting on the batch dimension means the
    exported model can accept single frames (batch=1) or batches
    of frames without needing to be re-exported. This is useful 
    for testing batched input during benchmarking.
    """
    model = YOLO(input_model)

    # Export using ultralytics built in ONNX export.
    # opset=17 is recommended for compatibility
    # with TensorRT 8.x and later. We will be running on CPU
    # so this doesn't matter as much.
    model.export(
        format="onnx",
        imgsz=640,
        # opset=17,
        dynamic=False, # non dynamic batch size
        simplify=True,
        batch=1, # we are always processing images one at a time
        # optimize=False # setting to optimize for DEEPX hardware
    )

if __name__=="__main__":
    export_perception_model(input_model="models/yolo11n.pt")

    

from ultralytics import YOLO

def export_perception_model(weights_path: str, output_path: str):
    """
    Exports a YOLOv11 model to ONNX format for edge deployment.

    The dynamic_axes setting on the batch dimension means the
    exported model can accept single frames (batch=1) or batches
    of frames without needing to be re-exported. This is useful 
    for testing batched input during benchmarking.
    """
    model = YOLO(weights_path)

    # Export using ultralytics built in ONNX export.
    # opset=17 is recommended for compatibility
    # with TensorRT 8.x and later. We will be running on CPU
    # so this doesn't matter as much.
    model.export(
        format="onnx",
        imgsz=640,
        opset=17,
        dynamic=True, # dynamic batch size
        simplify=True
    )

    print(f"Model exported to {output_path}")

if __name__=="__main__":
    export_perception_model(
        weights_path="models/yolo11n.pt",
        output_path="models/perception.onnx"
    )

    
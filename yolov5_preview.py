#!/usr/bin/env python3

'''
Author:   Maximilian Sittinger (https://github.com/maxsitt)
Website:  https://maxsitt.github.io/insect-detect-docs/
License:  GNU GPLv3 (https://choosealicense.com/licenses/gpl-3.0/)

This Python script does the following:
- run a custom YOLOv5 object detection model (.blob format) on-device (Luxonis OAK)
- use 4K frames downscaled to full FOV LQ frames (e.g. 320x320) as model input
- show a preview of 4K frames downscaled to full FOV LQ frames (e.g. 320x320) + model output
- optional argument:
  "-log" print available Raspberry Pi memory (MB) and RPi CPU utilization (percent) to console

compiled with open source scripts available at https://github.com/luxonis
'''

import argparse
import json
import time
from pathlib import Path

import cv2
import depthai as dai
import numpy as np

# Define optional arguments
parser = argparse.ArgumentParser()
parser.add_argument("-log", "--print_log", action="store_true",
    help="print RPi available memory (MB) + CPU utilization (percent)")
args = parser.parse_args()

if args.print_log:
    import psutil

# Set file paths to the detection model and config JSON
MODEL_PATH = Path("./insect-detect/models/yolov5n_320_openvino_2022.1_4shave.blob")
CONFIG_PATH = Path("./insect-detect/models/json/yolov5_320.json")

# Extract detection model metadata from config JSON
with CONFIG_PATH.open(encoding="utf-8") as f:
    config = json.load(f)
nn_config = config.get("nn_config", {})
nn_metadata = nn_config.get("NN_specific_metadata", {})
classes = nn_metadata.get("classes", {})
coordinates = nn_metadata.get("coordinates", {})
anchors = nn_metadata.get("anchors", {})
anchor_masks = nn_metadata.get("anchor_masks", {})
iou_threshold = nn_metadata.get("iou_threshold", {})
confidence_threshold = nn_metadata.get("confidence_threshold", {})
nn_mappings = config.get("mappings", {})
labels = nn_mappings.get("labels", {})

# Create depthai pipeline
pipeline = dai.Pipeline()

# Create and configure camera node
cam_rgb = pipeline.create(dai.node.ColorCamera)
#cam_rgb.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)
cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_4_K)
cam_rgb.setPreviewSize(320, 320) # downscaled LQ frames for model input
cam_rgb.setInterleaved(False)
cam_rgb.setPreviewKeepAspectRatio(False) # squash full FOV frames to square
cam_rgb.setFps(40) # frames per second available for focus/exposure/model input

# Create detection network node and define input + outputs
nn = pipeline.create(dai.node.YoloDetectionNetwork)
cam_rgb.preview.link(nn.input) # downscaled LQ frames as model input
nn.input.setBlocking(False)

xout_nn = pipeline.create(dai.node.XLinkOut)
xout_nn.setStreamName("nn")
nn.out.link(xout_nn.input)

xout_rgb = pipeline.create(dai.node.XLinkOut)
xout_rgb.setStreamName("frame")
nn.passthrough.link(xout_rgb.input)

# Set detection model specific settings
nn.setBlobPath(MODEL_PATH)
nn.setNumClasses(classes)
nn.setCoordinateSize(coordinates)
nn.setAnchors(anchors)
nn.setAnchorMasks(anchor_masks)
nn.setIouThreshold(iou_threshold)
nn.setConfidenceThreshold(confidence_threshold)
nn.setNumInferenceThreads(2)

# Define function to convert relative bounding box coordinates (0-1) to pixel coordinates
def frame_norm(frame, bbox):
    """Convert relative bounding box coordinates (0-1) to pixel coordinates."""
    norm_vals = np.full(len(bbox), frame.shape[0])
    norm_vals[::2] = frame.shape[1]
    return (np.clip(np.array(bbox), 0, 1) * norm_vals).astype(int)

# Connect to OAK device and start pipeline
with dai.Device(pipeline, usb2Mode=True) as device:

    # Create output queues to get the frames and detections from the outputs defined above
    q_frame = device.getOutputQueue(name="frame", maxSize=4, blocking=False)
    q_nn = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

    # Create start_time and counter variables to measure fps of the detection model
    start_time = time.monotonic()
    counter = 0

    # Get LQ preview frames and model output (detections) and show in window
    while True:
        if args.print_log:
            print(f"Available RPi memory: {round(psutil.virtual_memory().available / 1048576)} MB")
            print(f"RPi CPU utilization:  {psutil.cpu_percent(interval=None)}%")
            print("\n")

        frame = q_frame.get().getCvFrame()
        nn_out = q_nn.get()

        if nn_out is not None:
            dets = nn_out.detections
            counter += 1
            fps = counter / (time.monotonic() - start_time)

        if frame is not None:
            for detection in dets:
                bbox = frame_norm(frame, (detection.xmin, detection.ymin,
                                          detection.xmax, detection.ymax))
                cv2.putText(frame, labels[detection.label], (bbox[0], bbox[3] + 13),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                cv2.putText(frame, f"{round(detection.confidence, 2)}", (bbox[0], bbox[3] + 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)

            cv2.putText(frame, f"fps: {round(fps, 2)}", (4, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.imshow("yolov5_preview", frame)
            # streaming the frames via SSH (X11 forwarding) will slow down fps
            # comment out 'cv2.imshow()' and print fps to console for "true" fps
            #print(f"fps: {round(fps, 2)}")

        if cv2.waitKey(1) == ord("q"):
            break

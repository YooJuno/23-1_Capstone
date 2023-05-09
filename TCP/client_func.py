import argparse
import os
import serial
import numpy as np
import cv2
import torch.nn as nn
import csv
import base64
from io import BytesIO
import socket
from PIL import Image
import torch
from torch.autograd import Variable
import torchvision.transforms as T


transformations = T.Compose(
    [T.Lambda(lambda x: (x / 127.5) - 1.0)])


def detect(img):
    # Stop signal
    sign = 0
    
    # Load Yolo
    net = cv2.dnn.readNet("./yolo/yolov4-tiny.weights", "./yolo/yolov4-tiny.cfg")
    classes = []
    with open("./yolo/coco.names", "r") as f:
        classes = [line.strip() for line in f.readlines()]

    layer_names = net.getLayerNames()
    output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

    img = cv2.resize(img, (640, 480))

    height, width, channels = img.shape

    # Detecting objects
    blob = cv2.dnn.blobFromImage(img, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)

    # Showing informations on the screen
    class_ids = []
    confidences = []
    boxes = []
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.5:
                # Object detected
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)

                # Rectangle coordinates
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)

                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)

    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            if label == "person" and w>=40:
                sign = 1
                print("person1")
                break
            else:
                sign = 0

    return sign

def save_debug_autolog(self, path, prev_angle, model_output, diff_angle):
    with open(path, 'a', newline='') as csv_file:
        wr = csv.writer(csv_file)
        wr.writerow([self.path, str(prev_angle), str(model_output), str(diff_angle)])

def save_drivinglog(self, path, csv_angle):
    with open(path, 'a', newline='') as csv_file:
        wr = csv.writer(csv_file)
        wr.writerow([self.path, str(csv_angle)])

def save_drivingframe(self, frame):
    self.path = './data/frame' + str(self.cnt) + '.jpg'
    cv2.imwrite(self.path, frame)
    self.cnt += 1
    
def send_img_toSLAM(self, frame):
    encoded_image = cv2.imencode(".jpg", frame)[1].tobytes()
    size = len(encoded_image).to_bytes(4,byteorder='little')
    self.conn.send(size)
    self.conn.send(encoded_image)
    frame_str = base64.b64encode(encoded_image)
    frame = Image.open(BytesIO(base64.b64decode(frame_str)))
    return frame

def PilotNet_crop_img(frame):
    frame = frame.resize((320,160))
    image_array = np.array(frame.copy())
    # image_array = image_array[40:-50, :]
    image_array = image_array[65:-25, :] # 예전 코드
    crop_img = image_array.copy()
    return image_array, crop_img
    
def preprocess_PilotNetimg(image_array):
    image_array = image_array[:, :, ::-1]
    image_array = transformations(image_array)
    image_tensor = torch.Tensor(image_array)
    image_tensor = image_tensor.view(1, 3, 70, 320)
    image_tensor = Variable(image_tensor)
    return image_tensor

def postprocess_PilotNet(self, image_tensor, cur_angle):
    prev_angle = cur_angle # 저장용
    steering_angle = self.model(image_tensor).view(-1).data.numpy()[0] #angle
    # print('steering : ',steering_angle)
    steering_angle = steering_angle * 20 # 핸들이 돌아갈 수 있는 정도 : 차량 바퀴가 돌아가는 정도 = 20
    model_output = steering_angle # 저장용
    diff_angle = steering_angle - cur_angle
    diff_angle = int(diff_angle)
    cur_angle = steering_angle
    return diff_angle, cur_angle, prev_angle, model_output, diff_angle

def auto_control_car(ser, diff_angle, csv_angle) :
    #  if flag_boundary == 'IN':   
    if diff_angle > 0: #angle이 오른쪽으로 꺽여야함
        for i in range(diff_angle) :
            tmp = ser.write(b'd')
            # print("ser test = ", tmp)
            csv_angle += 0.25
            if csv_angle >= 1 :
                csv_angle = 1
    else : # angle이 왼쪽으로 꺽여야 함
        for i in range(-diff_angle) :
            ser.write(b'a')
            csv_angle -= 0.25
            if csv_angle <= -1 :
                csv_angle = -1
    # elif flag_boundary == 'LEFT':
    # elif flag_boundary == 'RIGHT':

    return csv_angle

def keyboard_control_car(ser, key, csv_angle):
    if key == 'w': 
        print("W")
        ser.write(b'w')
    elif key == 'a':
        print("A")
        ser.write(b'a')
        csv_angle -= 0.25
        if csv_angle <= -1 :
            csv_angle = -1
    elif key == 's':
        print("S")
        ser.write(b's')
    elif key == 'd':
        print("D")
        ser.write(b'd')
        csv_angle += 0.25
        if csv_angle >= 1 :
            csv_angle = 1
    elif key == 'x':
        print("X")
        ser.write(b'x')
    return csv_angle


def left_1(juno_x, margin):
    juno_z = -7.273 * (juno_x - margin)  -0.080
    return juno_z

def left_2(juno_x, margin):
    juno_z = -0.926 * (juno_x - margin)  + 0.143
    return juno_z

def left_3(juno_x, margin):
    juno_z = -0.068 * (juno_x)  + 0.346 + margin
    return juno_z

def left_4(juno_x, margin):
    juno_z = 0.605 * (juno_x)  + 0.653 + margin
    return juno_z

def left_5(juno_x, margin):
    juno_z = 0.111 * (juno_x)  + 0.319 + margin
    return juno_z

def right_1(juno_x, margin):
    juno_z = -26.857 * (juno_x + margin)  + 0.618
    return juno_z

def right_2(juno_x, margin):
    juno_z = -1.139 * (juno_x + margin)  + 0.232
    return juno_z

def right_3(juno_x, margin):
    juno_z = 0.072 * (juno_x)  + 0.484 - margin
    return juno_z

def right_4(juno_x, margin):
    juno_z = 0.759 * (juno_x)  + 0.799 - margin
    return juno_z

def right_5(juno_x, margin):
    juno_z = 0.040 * (juno_x)  + 0.305 - margin
    return juno_z

def bridge_1(juno_x, margin):
    juno_z = 0.343 * (juno_x - margin)  + 0.019
    return juno_z

def bridge_2(juno_x, margin):
    juno_z = 0.800 * (juno_x - margin)  + 0.203
    return juno_z

def bridge_3(juno_x, margin):
    juno_z = 3.690 * (juno_x - margin)  + 1.236
    return juno_z

def bridge_4(juno_x, margin):
    juno_z = -24.667 * (juno_x - margin)  -10.871
    return juno_z

def bridge_5(juno_x, margin):
    juno_z = -3.091 * (juno_x - margin)  -1.845
    return juno_z

def bridge_6(juno_x, margin):
    juno_z = -4.300 * (juno_x - margin)  -3.219
    return juno_z



def localization(juno_x, juno_z, out_cnt, area):
    print("x : ", juno_x, "\nz : " , juno_z)
    print()
    margin = 0.01
    support_margin = 0.05
    
    if ((juno_z > left_1(juno_x, margin)) and (juno_z < right_1(juno_x, margin)) and (juno_z < bridge_2(juno_x, margin))):
        out_cnt = 0
        area = "area1"
        print("area1")
    elif ((juno_z > left_2(juno_x, margin)) and (juno_z < right_2(juno_x, margin)) and (juno_z < bridge_3(juno_x, margin))):
        out_cnt = 0
        area = "area2"
        print("area2")
    elif ((juno_z > left_3(juno_x, margin)) and (juno_z < right_3(juno_x, margin) ) and (juno_z > bridge_4(juno_x, margin))) :
        out_cnt = 0
        area = "area3"
        print("area3")
    elif ((juno_z > left_4(juno_x, margin)) and (juno_z < right_4(juno_x, margin)) and (juno_z > bridge_5(juno_x, margin))):
        out_cnt = 0
        area = "area4"
        print("area4")
    elif ((juno_z > left_5(juno_x, margin)) and (juno_z < right_5(juno_x, margin)) and (juno_z > bridge_6(juno_x, margin))):
        out_cnt = 0
        area = "area5"
        print("area5")
    else :      
        out_cnt = out_cnt + 1
    
    print("area = " ,area)
    if ( area == "area1" ) and ( juno_z < left_1(juno_x, support_margin) )  :
        print("send d = 오른쪽으로 가.")
    elif  ( area == "area1" ) and ( juno_z > right_1(juno_x, support_margin) )  :
        print("send a = 왼쪽으로 가")

    elif ( area == "area2") and ( juno_z < left_2(juno_x, support_margin) ) :
        print("send a = 왼쪽으로 가")
    elif ( area == "area2") and ( juno_z > right_2(juno_x, support_margin) ) :
        print("send d = 오른쪽으로 가.")
        
    elif ( area == "area3") and ( juno_z < left_3(juno_x, support_margin) ):
        print("send d = 오른쪽으로 가.")
    elif ( area == "area3") and ( juno_z > right_3(juno_x, support_margin) ):
        print("send a = 왼쪽으로 가")

    elif ( area == "area4") and ( juno_z < left_4(juno_x, support_margin) ):
        print("send a = 왼쪽으로 가")
    elif ( area == "area4") and ( juno_z > right_4(juno_x, support_margin) ):
        print("send d = 오른쪽으로 가. ")

    elif ( area == "area5") and ( juno_z < left_5(juno_x, support_margin) ):
        print("send a = 왼쪽으로 가")
    elif ( area == "area5") and ( juno_z > right_5(juno_x, support_margin) ):
        print("send d = 오른쪽으로 가. ")
    return out_cnt

def serial_connect(os_type):
    if os_type == 'UBUNTU': # UBUNTU
        port_addr = "/dev/ttyACM0"
        os.system("sudo chmod 777 /dev/ttyACM0")
        # os.system("rm -rf debug_autolog.csv")
        os.system("rm -rf driving_log_all.csv")
        os.system("rm -rf driving_log_keyboard.csv")
        # os.system("rm -rf data")
    elif os_type == 'MAC': # MAC OS
        port_addr = "/dev/tty.usbmodem21403"
    ser = serial.Serial(
                        port=port_addr,
                        baudrate=9600,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize=serial.EIGHTBITS,
                        timeout=0
                    )
    if ser.isOpen() == False :
        ser.open()
    return ser

def parsing():
    parser = argparse.ArgumentParser(description='Auto Driving')
    parser.add_argument('--model',type=str,default='./model/model-a-100_1.h5',help='')
    parser.add_argument('--IP',type=str,default='127.0.0.1',help='')
    parser.add_argument('--PORT',type=str,default='1115',help='')
    return parser.parse_args()


class NetworkNvidia(nn.Module):
    """NVIDIA model used in the paper."""

    def __init__(self):
        """Initialize NVIDIA model.
        NVIDIA model used
            Image normalization to avoid saturation and make gradients work better.
            Convolution: 5x5, filter: 24, strides: 2x2, activation: ELU
            Convolution: 5x5, filter: 36, strides: 2x2, activation: ELU
            Convolution: 5x5, filter: 48, strides: 2x2, activation: ELU
            Convolution: 3x3, filter: 64, strides: 1x1, activation: ELU
            Convolution: 3x3, filter: 64, strides: 1x1, activation: ELU
            Drop out (0.5)
            Fully connected: neurons: 100, activation: ELU
            Fully connected: neurons: 50, activation: ELU
            Fully connected: neurons: 10, activation: ELU
            Fully connected: neurons: 1 (output)
        the convolution layers are meant to handle feature engineering.
        the fully connected layer for predicting the steering angle.
        the elu activation function is for taking care of vanishing gradient problem.
        """
        super(NetworkNvidia, self).__init__()
        self.conv_layers = nn.Sequential(
            nn.Conv2d(3, 24, 5, stride=2),
            nn.ELU(),
            nn.Conv2d(24, 36, 5, stride=2),
            nn.ELU(),
            nn.Conv2d(36, 48, 5, stride=2),
            nn.ELU(),
            nn.Conv2d(48, 64, 3),
            nn.ELU(),
            nn.Conv2d(64, 64, 3),
            nn.Dropout(0.5)
        )
        self.linear_layers = nn.Sequential(
            nn.Linear(in_features=64 * 2 * 33, out_features=100),
            nn.ELU(),
            nn.Linear(in_features=100, out_features=50),
            nn.ELU(),
            nn.Linear(in_features=50, out_features=10),
            nn.Linear(in_features=10, out_features=1)
        )

    def forward(self, input):
        """Forward pass."""
        input = input.view(input.size(0), 3, 70, 320)
        output = self.conv_layers(input)
        output = output.view(output.size(0), -1)
        output = self.linear_layers(output)
        return output
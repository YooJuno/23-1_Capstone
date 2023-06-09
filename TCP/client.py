#################### CLIENT ####################
#################### CLIENT ####################
#################### CLIENT ####################
#################### CLIENT ####################


import sys
import threading
import cv2
from PIL import Image
import numpy as np
import torch
from torch.autograd import Variable
import torchvision.transforms as T
import base64
from io import BytesIO
import socket
import csv
import client_func as capstone


transformations = T.Compose(
    [T.Lambda(lambda x: (x / 127.5) - 1.0)])


#FLAG_SERIAL = 'DISCONNECTED'
FLAG_SERIAL = 'CONNECTED'

# OS_TYPE = 'MAC' 
OS_TYPE = 'UBUNTU'

# driving_type = 'AUTO'
driving_type = 'MANUAL'

DRIVE_WITH_SLAM_TYPE = 'WITH'
#DRIVE_WITH_SLAM_TYPE = 'WITHOUT'

if OS_TYPE == 'UBUNTU':
    camera_num = 2
elif OS_TYPE == 'MAC':
    camera_num = 0

# for multi thread
Boundary = ''
lock = threading.Lock()
sock = 0
interval = 10
frame_yolo = 0 
detect_sign = 0
prev_detect = 0


# STM32F411RE 연결할지 말지
if FLAG_SERIAL == 'CONNECTED': # Connected to STM32
    ser = capstone.serial_connect(OS_TYPE)

# 이미지를 보내는 쓰레드
class ImageThread(threading.Thread):
    def __init__(self, model, args):
        threading.Thread.__init__(self)
        global sock
         # 서버에 연결  
        if DRIVE_WITH_SLAM_TYPE == 'WITH':      
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((args.IP, int(args.PORT)))
            self.conn = sock
        self.model = model
        self.cnt = 0
        self.path = ''
        

    def run(self):
        key = -1
        global Boundary # 쓰레드 공유변수
        global driving_type
        global frame

        cap = cv2.VideoCapture(camera_num)    
        # cap = cv2.VideoCapture('/home/yoojunho/바탕화면/v1.mp4')
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1024)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 768)
        
        
        # STM32 연결돼있고 AUTO모드이면 일단 출발
        if FLAG_SERIAL == 'CONNECTED' and driving_type == 'AUTO':
            ser.write(b'w')
            ser.write(b'w')

        # speedz flag
        prev_person = 0
        juno_person = 0
        cnt = 0
        cur_angle = 0
        csv_angle = 0
        
        while True:
            ret, frame = cap.read()
            key = cv2.waitKey(1)  
            cnt = cnt + 1
            if not ret:
                print("Failed to capture frame.")
                break
            
            #YOLO
            if driving_type == 'AUTO' :
                if cnt % 10 == 0:
                    juno_person = capstone.detect(frame)    
                    if juno_person == 1:
                        ser.write(b's') 
                    elif juno_person == 0 and prev_person == 1:
                        print("go again!!")
                        ser.write(b'w')
                    prev_person = juno_person

            #KEY preprocessing
            if (97 <= key <= 122) or (65 <= key <= 90):
                key = chr(key).lower()
            elif key == 27:
                break
            
            # frame 저장
            capstone.save_drivingframe(self,frame)

            # SLAM 이용하면 서버와 통신해야됨
            if DRIVE_WITH_SLAM_TYPE == 'WITH':
                frame = capstone.send_img_toSLAM(self,frame)

            # PilotNet에 넣기위해 crop
            image_array, crop_img = capstone.PilotNet_crop_img(frame)
            
            #자동
            if driving_type == 'AUTO' : 
                if key == 'p':
                    ser.write(b's')
                    driving_type = 'MANUAL'

                # PilotNet에 넣고, 예측 조향값 후처리
                image_tensor = capstone.preprocess_PilotNetimg(image_array)
                diff_angle, cur_angle = capstone.postprocess_PilotNet(self, image_tensor, cur_angle)
                
                # 예측 조향값 차량 제어
                if FLAG_SERIAL == 'CONNECTED' and Boundary == 'IN BOUNDARY':
                    csv_angle = capstone.auto_control_car(ser, diff_angle, csv_angle)
                
                # driving log 저장
                capstone.save_drivinglog(self, 'driving_log_all.csv',csv_angle)
                
            #수동
            elif driving_type == 'MANUAL' :
                if key == 'r':
                    driving_type = 'AUTO'
                    ser.write(b'w')
                    ser.write(b'w')
                else:
                    #수동차량제어
                    if FLAG_SERIAL == 'CONNECTED':
                        csv_angle = capstone.keyboard_control_car(ser, key,csv_angle)
                    #이탈복귀시퀀스 & 전체주행시퀀스 로그 저장        
                    capstone.save_drivinglog(self, 'driving_log_keyboard.csv',csv_angle)                    
                    capstone.save_drivinglog(self, 'driving_log_all.csv',csv_angle)
                        
            if OS_TYPE == 'UBUNTU':
                cv2.imshow("autodrive_crop", crop_img)

        if DRIVE_WITH_SLAM_TYPE == 'WITH':
            # 연결 종료
            self.conn.close()

# 좌표를 받는 쓰레드
class StringThread(threading.Thread):
    def __init__(self):
        global sock
        threading.Thread.__init__(self)
        self.conn = sock
        
    def run(self):
        
        global Boundary # 쓰레드 공유변수
        global driving_type
        # main.
        out_cnt = 0
        while True:
            data = self.conn.recv(1024).decode()
            self.conn.recv(1024).decode() # clear buffer
            
            if not data:
                break
            data = data.split(',')
            juno_x = float(data[0])
            juno_z = float(data[1])

            lock.acquire()
            Boundary = 'IN BOUNDARY' # 범위 안에 있음
            lock.release()
            
            #냬 위치 파악
            out_cnt = capstone.localization(juno_x, juno_z, out_cnt)
            
            # 좌표가 순간적으로 튀는 것을 방지하기 위해
            if out_cnt > 10:
                lock.acquire()
                Boundary = 'OUT OF BOUNDARY'
                lock.release()
                print(Boundary)
            # 나갔으면
            if FLAG_SERIAL== 'CONNECTED' and Boundary == 'OUT OF BOUNDARY' and driving_type == 'AUTO':
                ser.write(b's')
                driving_type = 'MANUAL'

        # 연결 종료
        self.conn.close()

if __name__ == '__main__':

    args = capstone.parsing()

    model = capstone.NetworkNvidia()

    if OS_TYPE == 'UBUNTU': # UBUNTU
        try:
            checkpoint = torch.load(
                args.model, map_location=lambda storage, loc: storage)
            model.load_state_dict(checkpoint['state_dict'])

        except KeyError:
            checkpoint = torch.load(
                args.model, map_location=lambda storage, loc: storage)
            model = checkpoint['model']

        except RuntimeError:
            print("==> Please check using the same model as the checkpoint")
            import sys
            sys.exit()
    
    elif OS_TYPE == 'MAC':
        checkpoint = torch.load(
            args.model, map_location=lambda storage, loc: storage)
        model.load_state_dict(checkpoint['state_dict'])


    # 이미지 보내는 쓰레드 시작
    image_thread = ImageThread(model, args)
    image_thread.start()
    
    if DRIVE_WITH_SLAM_TYPE == 'WITH':
        # 문자열 받는 쓰레드 시작
        string_thread = StringThread()
        string_thread.start()
        # yolo_thread = YoloThread()
        # yolo_thread.start()


# # yolo 쓰레드
# class YoloThread(threading.Thread):
#     def __init__(self):
#         global sock
#         threading.Thread.__init__(self)
#         self.conn = sock
        
#     def run(self):        
        
#         global detect_sign
#         global prev_detect
        
#         while True:
#             data_img = self.conn.recv(1024).decode()
#             self.conn.recv(1024).decode() # clear buffer
            
#             if not data_img:
#                 break
#             else:
#                 print("yolo thread working")
            
#             img = cv2.imdecode(data_img, 1)
            
#             detect_sign = capstone.detect(img)
            
#             if detect_sign == 1:
#                 ser.write(b's')
#                 prev_detect = detect_sign
#             elif detect_sign == 0 and prev_detect == 1:
#                 ser.write(b'w')


#         # 연결 종료
#         self.conn.close()

# # yolo 쓰레드
# class YoloThread(threading.Thread):
#     def __init__(self):
#         global sock
#         threading.Thread.__init__(self)
#         self.conn = sock
        
#     def run(self):        
        
#         global detect_sign
#         global prev_detect
        
#         while True:
#             data_img = self.conn.recv(1024).decode()
#             self.conn.recv(1024).decode() # clear buffer
            
#             if not data_img:
#                 break
#             else:
#                 print("yolo thread working")
            
#             img = cv2.imdecode(data_img, 1)
            
#             detect_sign = capstone.detect(img)
            
#             if detect_sign == 1:
#                 ser.write(b's')
#                 prev_detect = detect_sign
#             elif detect_sign == 0 and prev_detect == 1:
#                 ser.write(b'w')


#         # 연결 종료
#         self.conn.close()

import threading
import traceback
import logging
from datetime import datetime, timedelta,timezone
from datetime import timezone, timedelta, timedelta as td
import serial
import time
from ExtensionCls.MongoDB import MongoDB
from ExtensionCls.IsCheckTime import IsCheckTime
import json,base64
import atexit
import time
from Tesncryption.AsymmetricEncryption import AsymmetricEncryption,AESUtil
import hashlib
import RPi.GPIO as GPIO
from collections import deque
import queue
# GPIO.setmode(GPIO.BCM)  # PHẢI GỌI DÒNG NÀY TRƯỚC
# GPIO.setwarnings(False)
# gpio_pins = [17, 18, 27, 22, 23, 24, 25]
# for pin in gpio_pins:
#     GPIO.setup(pin, GPIO.OUT)
# for pin in gpio_pins:
#     GPIO.output(pin, GPIO.HIGH)

gpio_on=False
# def cleanup_gpio():
#     print("Chương trình kết thúc, cleanup GPIO...")
#     GPIO.cleanup()

# atexit.register(cleanup_gpio)
rfid_queue = queue.Queue(maxsize=20)
gpio_on = False
barrier_busy = False
GPIO.setwarnings(False)
GPIO.cleanup() 
gpio_pins = [17, 18, 27, 22, 23, 24, 25]
GPIO.setmode(GPIO.BCM)  # PHẢI GỌI DÒNG NÀY TRƯỚC
for pin in gpio_pins:
    GPIO.setup(pin, GPIO.OUT)

def on_pin():
    # global gpio_on
    # logging.info("**====== Mo cua ======**")
    # gpio_on=True
    # GPIO.setmode(GPIO.BCM)  # PHẢI GỌI DÒNG NÀY TRƯỚC
    # GPIO.setwarnings(False)
    # gpio_pins = [17, 18, 27, 22, 23, 24, 25]
    # for pin in gpio_pins:
    #     GPIO.setup(pin, GPIO.OUT)
    try:
        for pin in gpio_pins:
            GPIO.output(pin, GPIO.HIGH)
        logging.info(">>> Barrier OPEN")   
    except:
        logging.error(">>>----ERROR Barrier OPEN")
def off_pin():
    # global gpio_on
    # logging.info("**====== Dong cua ======**")
    # gpio_on=False
    # GPIO.setmode(GPIO.BCM)  # PHẢI GỌI DÒNG NÀY TRƯỚC
    # GPIO.setwarnings(False)
    # gpio_pins = [17, 18, 27, 22, 23, 24, 25]
    # for pin in gpio_pins:
    #     GPIO.setup(pin, GPIO.OUT)
    try:
        for pin in gpio_pins:
            GPIO.output(pin, GPIO.LOW)
        logging.info(">>> Barrier CLOSE")
    except:
        logging.error(">>>----ERROR Barrier CLOSE")

# entrylog_file="/home/meg/UHF_RFID_CHECK/ExtensionCls/backup_entry.json"
# config_file="/home/meg/UHF_RFID_CHECK/ExtensionCls/configs.json"
# database_file="/home/meg/UHF_RFID_CHECK/ExtensionCls/database.json"
entrylog_file="backup_entry.json"
config_file="configs.json"
database_file="database.json"
# with open('/home/meg/UHF_RFID_CHECK/ExtensionCls/configs.json', 'r', encoding='utf-8') as file:
with open(config_file, 'r', encoding='utf-8') as file:
    configs = json.load(file)
port_name = configs['port']
baudrate = configs['baudrate']
_name_parking = configs['name_parking']
ServerUri = configs['server']['uri']
DBname = configs['server']['db_name']
# log_filename = "Logs/Car_parking.log"
log_filename = "Car_parking.log"
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)
in_ok = "NO"
out_ok = "NO"
data_send = ""
def load_aes_key_iv():
    with open('/home/meg/Carparking_SEVT/Keys/aes_key_iv.json') as f:
        data = json.load(f)
    key = base64.b64decode(data['key'])
    return key
with open("/home/meg/Carparking_SEVT/Keys/public_key.pem", "r") as f:
    public_key = f.read()

with open("/home/meg/Carparking_SEVT/Keys/private_key.pem", "r") as f:
    private_key = f.read()
def hash_sha256(data: str) -> bytes:
    return hashlib.sha256(data.encode('utf-8')).digest()
key_aes= load_aes_key_iv()
aesUtil = AESUtil(key=key_aes)

class ControlCar:
    NameParking = '1'
    connected = True

    def __init__(self, nameparking, checktime_set):
        self.MongoDBServer = None
        self.NameParking = nameparking
        self.ModulCheck = IsCheckTime(self.NameParking)
        self.checktime_set = checktime_set
        try:
            MongoDBServer = MongoDB(uri=ServerUri, db_name=DBname)

            self.vehicles = MongoDBServer.get_collection("EmployeeParking")
            self.entry_logs = MongoDBServer.get_collection("EntryLogs")
            self.parking_status = MongoDBServer.get_collection("ParkingStatus")
            self.connected = True

            print("connected")
        except Exception as e:
            self.open_barrier()
            connected = False
            logging.error("KHONG THE KET NOI VOI SERVER: {}".format(e))
        # self.ImportLog=ImportLogs(nameparking)
    # **********************************************************
    # ================== BAT TAT BARRIER =======================
    # ***********************************************************
    def open_barrier(self):
        on_pin()
    
    # **********************************************************
    # ============= KIEM TRA SLOT BAI XE =======================
    # ***********************************************************
    def is_parking_available(self):
        try:
            status = self.parking_status.find_one({"name_parking": self.NameParking})
            return status["occupied_slots"] < status["total_slots"], status["total_slots"] - status["occupied_slots"]
        except Exception as e:
            return False,0

    # **********************************************************
    # =========== KIEM TRA XE CO LOG HAY CHUA ==================
    # ***********************************************************
    def is_exist_in(self, id_card_check):
        try:
            check = self.entry_logs.find_one({"id_card.sha": hash_sha256(id_card_check),"name_parking": self.NameParking})
            if check:
                return True
            return False
        except Exception as e:
            logging.error("CHECK EXITS LOG:{}".format(e))
            return False

    # *************************************************
    # ============= LUU DU LIEU =======================
    # *************************************************
    def save_data(self,  id_card, checkin_time, checkout_time, state=None,status=None):
        try:
            self.entry_logs.insert_one({
                "id_card": {
                    "aes": aesUtil.encrypt(id_card),
                    "sha": hash_sha256(id_card)
                },
                "name_parking": self.NameParking,
                "checkin_time": checkin_time,
                "checkout_time": checkout_time,
                "status_in":status
            })
            if state is not None:
                self.vehicles.update_one(
                    {"id_card.sha": hash_sha256(id_card)},
                    {"$set": {
                        "checkin_status": state
                    }}, upsert=True)
            # count = self.vehicles.count_documents({
            #     "name_parking": self.NameParking,
            #     "car_parked": True
            # })
            try:
                pipeline = [
                    {
                        "$match": {
                            "name_parking": self.NameParking,
                            "checkin_time": {"$ne": None},
                            "checkout_time": None,
                            "status_in":"valid"
                        }
                    },
                    {"$sort": {"checkin_time": -1}},
                    {
                        "$group": {
                            "_id": "$id_card.sha",
                            "latest_log": {"$first": "$$ROOT"}
                        }
                    },
                    {"$count": "total"}
                ]
                result_pip = list(self.entry_logs.aggregate(pipeline))
                count = result_pip[0]["total"] if result_pip else 0
                logging.info("========****DATA RAW: {} ****========".format(count))
            except Exception as e:
                print(" {}".format(traceback.format_exc()))
            self.parking_status.update_one(
                {"name_parking": self.NameParking},
                {"$set": {"occupied_slots": count}}
            )
            return True
        except Exception as e:
            return False

    # ********************************************
    # ============= XE VAO =======================
    # ********************************************
    def checkin_car(self, id_car_check):
        try:
            global in_ok, out_ok
            datetimee = datetime.now(timezone.utc)
            is_parking_available, slots = self.is_parking_available()
            if not is_parking_available:
                logging.info("Bai xe {} da day".format(self.NameParking))
                self.save_data( id_card=id_car_check, checkin_time=datetimee, checkout_time=None, status="full")
                # return
            logging.info("Bai xe con trong: {} cho".format(slots))
            
            vehicle=None
            try:
                if vehicle is None:
                    _id_car_check=id_car_check[-8:]
                    vehicle = self.vehicles.find_one({"id_card.sha": hash_sha256(_id_car_check),"type_card.sha": hash_sha256("epass"), "name_parking": self.NameParking})
                    if vehicle:
                        id_car_check=_id_car_check
            except:
                self.open_barrier()
                logging.error("KHONG THE KET NOI SERVER! \n ID Card vao: {}".format(id_car_check))
            try:
                if vehicle is None:
                    vehicle = self.vehicles.find_one({"id_card.sha": hash_sha256(id_car_check),"name_parking": self.NameParking})
            except:
                self.open_barrier()
                logging.error("KHONG THE KET NOI SERVER! \n ID Card vao: {}".format(id_car_check))
            if not vehicle:
                self.save_data( id_card=id_car_check, checkin_time=datetimee, checkout_time=None, status="invalid")
                logging.info("Xe khong ton tai trong he thong!")
                
                return
            # Kiem tra han su dung bai xe
            start_date = vehicle["start_date"]
            end_date = vehicle["end_date"]
            
            #if start_date.tzinfo is None:
            #    start_date = start_date.replace(tzinfo=timezone.utc)
            #if end_date.tzinfo is None:
            #    end_date = end_date.replace(tzinfo=timezone.utc)

          
            #if datetimee <= end_date:
            #    logging.info("===Xe con han===")
            #else:
            #    logging.info("===Xe het han===")
            #Kiem tra trang thai xe
            if str(vehicle["status"]).lower()=="blocked"  or str(vehicle["status"]).lower()=="block"  :
                # logging.info("Khong duoc phep vao bai".format(expiry))
                self.save_data( id_card=id_car_check, checkin_time=datetimee, checkout_time=None, status="blocked")
                return
            # Kiem tra xe vao bai

            self.open_barrier()
            save_data = self.save_data(id_card=id_car_check, state=True,  checkin_time=datetimee,checkout_time=None, status="valid")
            if save_data:
                in_ok = "INOK"
                logging.info("Thoi gian vao:{}".format(datetimee))
            else:
                logging.warning("KHONG LUU DUOC DU LIEU!")
        except Exception as e:
            logging.error("{}".format(traceback.format_exc()))
      


def thread_checkin(com, baudrate):
    global in_ok, data_send,gpio_on
    id_in_temp = "-1"
    #off_pin()

    reset_second = time.time()
    
    # for pin in gpio_pins:
    #     GPIO.setup(pin, GPIO.OUT)
    # for pin in gpio_pins:
    #     GPIO.output(pin, GPIO.HIGH)
    ser_rfid=None
    try:
        ser_rfid = serial.Serial(port=com, baudrate=baudrate, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                             bytesize=serial.EIGHTBITS, timeout=1)
        off_pin()
    except Exception as e:
        ser_rfid=None
        on_pin()
        logging.error("KHONG THE KET NOI CONG COM: {}".format(e))
    while True:
        if ser_rfid is not None:
            data_bytes = ser_rfid.read(18)
            data = data_bytes[4:-2].hex().lower()
            # data = ser_rfid.readline().decode('utf-8').strip()
            # if len(data) == 24:
            # if len(data)>1 and len(data)<24:
            #     logging.info("========****DATA RAW: {} ****========".format(data))
            if data!="" and data != None:
                if len(data) ==24:
                    data_check=data
                    if data_check != id_in_temp:
                        if gpio_on==False:
                            on_pin()
                        logging.info("ID nhan duoc: {}".format(data))
                        checkin = ControlCar(nameparking=_name_parking, checktime_set=45)
                        checkin.checkin_car(data)
                        id_in_temp = data_check
                        time.sleep(0.5)
                        if gpio_on==True:
                            gpio_on=False
                            off_pin()
                            
            if time.time() - reset_second > 20:
                id_in_temp = ""
                reset_second = time.time()
                # if gpio_on==True:
                #     off_pin()


#======================== TEST Chuong trinh ============================
#====================================================================
current_tag=None
last_seen=0
last_action=0
timeout=3
timedelay_btw=2
state="IDLE"
isSerial = False
def main():
    try:
        while True:
            global current_tag,last_seen,last_action,timeout,state,isSerial
            ser_rfid=None
            try:
                ser_rfid = serial.Serial(port=port_name, baudrate=baudrate, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                    bytesize=serial.EIGHTBITS, timeout=1)
                off_pin()
                logging.info(">>>>SERIAL OK")
                isSerial=False
            except Exception as e:
                if isSerial ==False:
                    logging.error(">>>> Serial: {}".format(e))
                    isSerial=True
                    on_pin()
                ser_rfid=None
                    
                
            if ser_rfid is not None:
                try:
                    while True:
                        now = time.time()
                        data_bytes = ser_rfid.read(18)
                        tag = data_bytes[4:-2].hex().lower()
                        #tag=ser_rfid.readline().decode().strip()
                        print(tag)
                        if state =="IDLE":
                            if tag and len(tag)==24 and tag.startswith("341"):
                                current_tag=tag
                                #on_pin()
                                logging.info("========================== ID nhan duoc: {} =====================================".format(tag))
                                checkin = ControlCar(nameparking=_name_parking, checktime_set=45)
                                logging.info(">>>>===Step 1")
                                checkin.checkin_car(tag)
                                state ="CARD_HELD"
                                last_seen = now
                        elif state =="CARD_HELD":
                            if tag == current_tag:
                                last_seen=now
                                last_action = now
                            elif not tag and now - last_seen > timeout:
                                off_pin()
                                current_tag=None
                                state ="IDLE"
                                logging.info(">>>>===Step 2")
                            elif tag and len(tag)==24 and tag.startswith("341") and tag != current_tag and now  -last_action>timedelay_btw:
                                #on_pin()
                                logging.info(">>>>===Step 3")
                                logging.info("========================== ID nhan duoc: {} ========================== ".format(tag))
                                checkin = ControlCar(nameparking=_name_parking, checktime_set=45)
                                checkin.checkin_car(tag)
                                
                                current_tag=tag
                                last_seen=now
                                last_action=now
                        time.sleep(0.5)

                except Exception as e:

                    logging.error("LOI XU LY CHECKIN: {}".format(e))
    except Exception as ex:
        print("FAIL COM")
                
#====================================================================================

def _main():
    
    thread = threading.Thread(target=thread_checkin, args=(port_name, baudrate))
    # thread = threading.Thread(target=thread_checkin, args=("COM1", 9600))
    thread.start()

if __name__ == '__main__':
    # main_oneway("/dev/ttyUSB0", 57600)
  
    main()
    # GPIO.cleanup()


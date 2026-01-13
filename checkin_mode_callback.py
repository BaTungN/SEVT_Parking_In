import threading
import traceback
import logging
from datetime import datetime, timedelta
import serial
import time
from ExtensionCls.MongoDB import MongoDB
from ExtensionCls.IsCheckTime import IsCheckTime
import json
import atexit
import os

import RPi.GPIO as GPIO

gpio_pins = [17, 18, 27, 22, 23, 24, 25]
gpio_on=False
def cleanup_gpio():
    print("Chương trình kết thúc, cleanup GPIO...")
    GPIO.cleanup()

atexit.register(cleanup_gpio)

def on_pin():
    global gpio_on
    print("Mo cua")
    gpio_on=True
    for pin in gpio_pins:
        GPIO.output(pin, GPIO.LOW)

def off_pin():
    global gpio_on
    print("Dong cua")
    gpio_on=False
    for pin in gpio_pins:
        GPIO.output(pin, GPIO.HIGH)

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
name_parking = configs['name_parking']
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


# ============= BACKUP DATABASE =======================
def convert_datetimes(doc):
    for key, value in doc.items():
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
    return doc

def backup_data(name_parking:str):
    COLLECTIONS = ["parking_status", "vehicles"]
    output_file = "database.json"
    backup_result = {}

    for col in COLLECTIONS:
        collection = MongoDB().get_collection(col)

        # Chỉ lấy các document có name_parking = "A"
        filtered_docs = collection.find({"name_parking": name_parking}, {"_id": 0})

        # Chuyển datetime về dạng chuỗi ISO
        docs = [convert_datetimes(doc) for doc in filtered_docs]

        backup_result[col] = docs

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(backup_result, f, indent=2, ensure_ascii=False)

class ControlCar:
    NameParking = 'A'
    connected = True

    def __init__(self, nameparking, checktime_set):
        self.MongoDBServer = None
        self.NameParking = nameparking
        self.ModulCheck = IsCheckTime(self.NameParking)
        self.checktime_set = checktime_set
        try:
            MongoDBServer = MongoDB(uri=ServerUri, db_name=DBname)
            # datetimeee = MongoDBServer.get_date_time()
            # newtime_os = datetimeee.strftime("%Y-%m-%d %H:%M:%S")
            # print(newtime_os)
            # os.system("sudo date -s '{}'".format(newtime_os))
            self.vehicles = MongoDBServer.get_collection("vehicles")
            self.entry_logs = MongoDBServer.get_collection("entry_logs")
            self.parking_status = MongoDBServer.get_collection("parking_status")
            self.connected = True
            backup_data(self.NameParking)
            self.upload_backup_to_server(name_parking=self.NameParking)

            self.clear_file()
            print("connected")
        except Exception as e:
            connected = False
            with open("database.json", mode='r', encoding='utf-8') as f:
                data = json.load(f)
            self.vehicles_backup = data['vehicles']
            self.parking_status_backup = data["parking_status"]
            # logging.error("{}".format(traceback.format_exc()))
            logging.error("KHONG THE KET NOI VOI SERVER: {}".format(e))
        # self.ImportLog=ImportLogs(nameparking)

    # ***********************************************************
    # =========== LUU DATA KHI DA CO KET NOI INTERNET ===========
    # ***********************************************************
    def upload_backup_to_server(self, filename=entrylog_file,name_parking="A"):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return

                data_list = json.loads(content)

                if isinstance(data_list, list) or isinstance(data_list, dict):

                    for data in data_list:
                        try:
                            logs = self.entry_logs.find({
                                "id_card": data["id_card"],
                                "name_parking": name_parking}).sort([("checkin_time", -1)])
                            listt = list(logs)

                            if not bool(listt):
                                return
                            log = listt[0]
                            print(log)
                            if log["checkout_time"] is not None:
                                if not isinstance(data["checkin_time"], datetime):
                                    data["checkin_time"] = datetime.fromisoformat(data["checkin_time"])
                                self.entry_logs.insert_one(data)
                                logging.info("LUU DATA LEN SERVER THANH CONG: {}".format(data))
                            elif self.ModulCheck.is_time_available(log["checkin_time"], data["checkin_time"], minutes = self.checktime_set):
                                if not isinstance(data["checkin_time"], datetime):
                                    data["checkin_time"] = datetime.fromisoformat(data["checkin_time"])
                                self.entry_logs.insert_one(data)
                                self.vehicles.update_one({"id_card":data["id_card"],"name_parking": name_parking},{"$set":{"car_parked": True}})
                                count = self.vehicles.count_documents({
                                    "name_parking": self.NameParking,
                                    "car_parked": True
                                })
                                self.parking_status.update_one(
                                    {"name_parking": "A"},
                                    {"$set": {"occupied_slots": count}}
                                )
                                logging.info("DAY DATA LEN SERVER THANH CONG: {}".format(data))
                            else:
                                return
                        except Exception as e:
                            logging.error("{}".format(traceback.format_exc()))
                else:
                    logging.error("Khong the doc file")
        except Exception as e:
            logging.error("{}".format(traceback.format_exc()))


    # ***********************************************************
    # ============= LUU ENTRY LOG OFFLINE =======================
    # ***********************************************************
    def append_backup_entry(self,data: dict, filename="backup_entry.json"):
        if os.path.exists(filename):
            # Đọc nội dung hiện tại
            with open(filename, "r", encoding="utf-8") as f:
                try:
                    entries = json.load(f)
                    if not isinstance(entries, list):
                        entries = []
                except json.JSONDecodeError:
                    entries = []
        else:
            entries = []
        entries.append(data)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=4)

    # ***********************************************************
    # ============= XOA FILE LOG OFF LINE =======================
    # ***********************************************************
    def clear_file(self, filename=entrylog_file):
        """Xóa trắng nội dung file."""

        with open(filename, "w", encoding="utf-8") as f:
            f.write("")

    # **********************************************************
    # ============= KIEM TRA SLOT BAI XE =======================
    # ***********************************************************
    def is_parking_available(self):
        try:
            status = self.parking_status.find_one({"name_parking": self.NameParking})
            return status["occupied_slots"] < status["total_slots"], status["total_slots"] - status["occupied_slots"]
        except Exception as e:
            logging.error("USING OFFLINE DATA")
            for data in self.parking_status_backup:
                if data['name_parking'] == self.NameParking:
                    return data["occupied_slots"] < data["total_slots"], data["total_slots"] - data["occupied_slots"]
            return False,0

    # **********************************************************
    # =========== KIEM TRA XE CO LOG HAY CHUA ==================
    # ***********************************************************
    def is_exist_in(self, id_card_check):
        try:
            check = self.entry_logs.find_one({"id_card": id_card_check,"name_parking": self.NameParking})
            if check:
                return True
            return False
        except Exception as e:
            try:
                with open(entrylog_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content !="":
                        return False  # File rỗng

                    data_log = json.loads(content)
                    for data in data_log:
                        if data["id_card"] == id_card_check :
                            return True
            except Exception as file_error:
                logging.error("File log offline trống: {}".format(file_error))
            return False

    # *************************************************
    # ============= LUU DU LIEU =======================
    # *************************************************
    def save_data(self, license_plate, id_card, checkin_time, checkout_time, status="OK", state=None, slot=None):
        try:
            self.entry_logs.insert_one({
                "license_plate": license_plate,
                "id_card": id_card,
                "name_parking": self.NameParking,
                "status": status,
                "checkin_time": checkin_time,
                "checkout_time": checkout_time,
            })
            if state is not None:
                self.vehicles.update_one(
                    {"id_card": id_card},
                    {"$set": {
                        "car_parked": state
                    }}, upsert=True)

            # Cáº­p nháº­t sá»‘ lÆ°á»£ng xe trong bÃ£i
            count = self.vehicles.count_documents({
                "name_parking": self.NameParking,
                "car_parked": True
            })
            self.parking_status.update_one(
                {"name_parking": "A"},
                {"$set": {"occupied_slots": count}}
            )
            return True
        except Exception as e:
            if checkin_time is not None:
                checkin_time= checkin_time.isoformat()
            if checkout_time is not None:
                checkout_time=checkout_time.isoformat()
            self.append_backup_entry({
                "license_plate": license_plate,
                "id_card": id_card,
                "name_parking": self.NameParking,
                "status": status,
                "checkin_time": checkin_time,
                "checkout_time": checkout_time,
            })

            for data in self.vehicles_backup:
                if data["id_card"]==id_card:
                    data["car_parked"]=state
            return False

    # ********************************************
    # ============= XE VAO =======================
    # ********************************************
    def checkin_car(self, id_car_check):
        try:
            global in_ok, out_ok
            is_parking_available, slots = self.is_parking_available()
            if not is_parking_available:
                logging.info("Bai xe {} da day".format(self.NameParking))
                return
            logging.info("Bai xe con trong: {} cho".format(slots))
            try:
                datetimee = self.MongoDBServer.get_date_time()
            except:
                datetimee = datetime.now()
            vehicle=None
            try:
                vehicle = self.vehicles.find_one({"id_card": id_car_check, "name_parking": self.NameParking})
            except:
                for data in self.vehicles_backup:
                    if data["id_card"]==id_car_check and data['name_parking']==self.NameParking:
                        vehicle = data

            if not vehicle:
                self.save_data(license_plate=None, id_card=id_car_check, checkin_time=datetimee, checkout_time=None,
                               status="ERROR")
                logging.info("Xe khong ton tai trong he thong!")
                return
            # print("id_card: {}".format(vehicle["id_card"]))
            # Kiem tra han su dung bai xe
            # Kiểm tra nếu registration_date là kiểu datetime
            if isinstance(vehicle["registration_date"], datetime):
                pass
            else:
                vehicle["registration_date"] = datetime.fromisoformat(vehicle["registration_date"])
            expiry = self.ModulCheck.is_expiry_available(vehicle["registration_date"], datetime_now=datetimee, months=6)
            temp = "OK"
            if expiry <= timedelta(0):
                logging.warning("Xe het han su dung bai: {}".format(expiry * (-1)))
                temp = "WARNING"
                return
            else:
                logging.info("Xe con han su dung bai: {}".format(expiry))

            # Kiem tra xe vao bai
            if vehicle["car_parked"] is False:
                save_data = self.save_data(vehicle["license_plate"], vehicle["id_card"], state=True,
                                           checkin_time=datetimee,
                                           checkout_time=None, slot=1, status=temp)
                if save_data:
                    in_ok = "INOK"
                    # print("Bien so: {}\nThoi gian vao:{}".format(vehicle["license_plate"], datetimee))
                    logging.info("Bien so: {}\nThoi gian vao:{}".format(vehicle["license_plate"], datetimee))
                else:
                    logging.warning("OFFLINE SAVE: \nBien so: {}\nLuu du lieu vao thanh cong".format(
                        vehicle["license_plate"]))

            else:
                # Kiem tra xem co log hay chua
                if self.is_exist_in(vehicle["id_card"]) is False:
                    save_data = self.save_data(vehicle["license_plate"], vehicle["id_card"], state=True,
                                               checkin_time=datetimee, checkout_time=None, slot=0, status=temp)
                    if save_data:
                        in_ok = "INOK"
                        # print("WARNING: Bien so: {}\nThoi gian vao:{}".format(vehicle["license_plate"], datetimee))
                        logging.warning(
                            "Bien so: {}\nThoi gian vao:{}".format(vehicle["license_plate"], datetimee))
                    else:
                        logging.warning("OFFLINE SAVE: \nBien so: {}\nLuu du lieu vao thanh cong".format(
                            vehicle["license_plate"]))
                else:

                    # Tim thoi gian ra gan nhat
                    try:
                        logs = self.entry_logs.find({
                            "id_card": vehicle["id_card"],
                            "name_parking": self.NameParking}).sort([("checkin_time", -1)])
                        listt = list(logs)
                        if not bool(listt):
                            return
                        log = listt[0]
                    except:
                        with open(entrylog_file,'r',encoding='utf-8') as f:
                            data_log=json.load(f)
                        matched_entries = [
                            entry for entry in data_log
                            if entry["id_card"] == vehicle["id_card"]
                               and entry["name_parking"] == self.NameParking
                        ]
                        matched_entries.sort(
                            key=lambda x: datetime.fromisoformat(x["checkin_time"]),
                            reverse=True
                        )
                        log = matched_entries[0]
                    if self.ModulCheck.is_time_available(log["checkin_time"], datetimee, minutes=self.checktime_set):
                        save_data = self.save_data(vehicle["license_plate"], vehicle["id_card"], state=True,
                                                   checkin_time=datetimee, checkout_time=None, slot=0, status=temp)
                        if save_data:
                            logging.warning(
                                "WARNING: Bien so: {}\nThoi gian vao:{}".format(vehicle["license_plate"],
                                                                                       datetimee))
                            # print("WARNING: Bien so: {}\nThoi gian vao:{}".format(vehicle["license_plate"], datetimee))

                        else:
                            logging.warning("OFFLINE SAVE: \nBien so: {}\nLuu du lieu vao khong thanh cong".format(
                                vehicle["license_plate"]))
                    else:
                        logging.info("Bien so: {}\nDang trong bai".format(vehicle["license_plate"]))
                        return
        except Exception as e:
            logging.error("{}".format(traceback.format_exc()))


def thread_checkin(com, baudrate):
    global in_ok, data_send,gpio_on
    id_in_temp = "-1"
    ser_rfid = serial.Serial(port=com, baudrate=baudrate, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                             bytesize=serial.EIGHTBITS, timeout=1)

    reset_second = time.time()
    GPIO.setmode(GPIO.BCM)  # PHẢI GỌI DÒNG NÀY TRƯỚC
    GPIO.setwarnings(False)
    for pin in gpio_pins:
        GPIO.setup(pin, GPIO.OUT)
    while True:
        # data_bytes = ser_rfid.read(18)
        # data = data_bytes[4:-2].hex().upper()
        data = ser_rfid.readline().decode('utf-8').strip()
        # if len(data) == 24:
        if len(data) >4:
            if data != id_in_temp:
                if gpio_on==False:
                    on_pin()
                logging.info("ID nhan duoc: {}".format(data))
                checkin = ControlCar(nameparking="A", checktime_set=45)
                checkin.checkin_car(data)
                id_in_temp = data
        if time.time() - reset_second > 5:
            id_in_temp = ""
            reset_second = time.time()
            if gpio_on==True:
                off_pin()



def main():
    
    thread = threading.Thread(target=thread_checkin, args=(port_name, baudrate))
    # thread = threading.Thread(target=thread_checkin, args=("COM1", 9600))
    thread.start()

if __name__ == '__main__':
    # main_oneway("/dev/ttyUSB0", 57600)
    
    main()
    GPIO.cleanup()


import threading
import traceback
import logging
from datetime import datetime, timedelta
import serial
import time
from ExtensionCls.MongoDB import MongoDB
from ExtensionCls.IsCheckTime import IsCheckTime
import json
import RPi.GPIO as GPIO
gpio_pins = [17, 18, 27, 22, 23, 24, 25]
import os
GPIO.setmode(GPIO.BCM)
for pin in gpio_pins:
    GPIO.setup(pin, GPIO.OUT)
def on_pin():
    for pin in gpio_pins:
        GPIO.output(pin, GPIO.HIGH)
def off_pin():
    for pin in gpio_pins:
        GPIO.output(pin, GPIO.LOW)
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

def backup_data():
    COLLECTIONS = ["parking_status", "vehicles"]
    output_file = "database.json"
    backup_result = {}

    for col in COLLECTIONS:
        collection = MongoDB().get_collection(col)

        # Chỉ lấy các document có name_parking = "A"
        filtered_docs = collection.find({"name_parking": "A"}, {"_id": 0})

        # Chuyển datetime về dạng chuỗi ISO
        docs = [convert_datetimes(doc) for doc in filtered_docs]

        backup_result[col] = docs

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(backup_result, f, indent=2, ensure_ascii=False)

class ControlCar:
    NameParking = 'A'
    connected = True

    def __init__(self, nameparking, checktime_set):
        self.NameParking = nameparking
        self.ModulCheck = IsCheckTime(self.NameParking)
        self.checktime_set = checktime_set
        try:
            MongoDBServer = MongoDB(uri=ServerUri, db_name=DBname)
            # from ExtensionCls.Logs import DBLogs
            # datetimeee = MongoDBServer.get_date_time()
            # newtime_os = datetimeee.strftime("%Y-%m-%d %H:%M:%S")
            # print(newtime_os)
            # os.system("sudo date -s '{}'".format(newtime_os))
            self.vehicles = MongoDBServer.get_collection("vehicles")
            self.entry_logs = MongoDBServer.get_collection("entry_logs")
            self.parking_status = MongoDBServer.get_collection("parking_status")
            self.connected = True
            print("connected")
            backup_data()

        except Exception as e:
            connected = False
            with open("database.json", mode='r', encoding='utf-8') as f:
                data = json.load(f)
            self.vehicles_backup = data['vehicles']
            self.parking_status_backup = data["parking_status"]
            logging.error("{}".format(traceback.format_exc()))
        # self.ImportLog=ImportLogs(nameparking)


    # ============= LUU ENTRY LOG OFFLINE =======================
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
    # ============= XOA FILE LOG OFF LINE ==============
    def clear_file(self, filename="backup_entry.json"):
        """Xóa trắng nội dung file."""
        if os.path.exists(filename):
            with open(filename, "w", encoding="utf-8"):
                pass  # Không ghi gì vào file -> xóa trắng
        else:
            print(f"File '{filename}' không tồn tại.")
    # ============= KIEM TRA SLOT BAI XE =======================
    def is_parking_available(self):
        try:
            status = self.parking_status.find_one({"name_parking": self.NameParking})
            return status["occupied_slots"] < status["total_slots"], status["total_slots"] - status["occupied_slots"]
        except Exception as e:
            logging.error("USING OFFLINE DATA: \nKiem tra bai xe con trong hay khong")
            for data in self.parking_status_backup:
                print(data)
                if data['name_parking'] == self.NameParking:
                    return data["occupied_slots"] < data["total_slots"], data["total_slots"] - data["occupied_slots"]
            return False,0
    # ============= THEM DU LIEU RA =======================
    def insert_checkout(self, vehicle, state, checkout_time, slot):
        # TÃ¬m entry log gáº§n nháº¥t chÆ°a cÃ³ giá» ra
        logs = self.entry_logs.find({
            "id_card": vehicle["id_card"],
            "name_parking": self.NameParking,
            "checkout_time": None}).sort({"checkin_time": -1})
        listt = list(logs)
        if not bool(listt):
            print("Xe khong co log vao bai!")
            return False
        log = listt[0]
        self.entry_logs.update_one(
            {"id_card": log["id_card"],
             "name_parking": self.NameParking,
             "checkin_time": log["checkin_time"]},
            {"$set": {"checkout_time": checkout_time}},
            upsert=True
        )

        self.vehicles.update_one(
            {"id_card": vehicle["id_card"],
             "name_parking": self.NameParking},
            {"$set": {
                "car_parked": state
            }}, upsert=True)
        # Cáº­p nháº­t sá»‘ lÆ°á»£ng xe trong bÃ£i
        self.parking_status.update_one({}, {"$inc": {"occupied_slots": slot}})
        return True

    # ============= KIEM TRA XE CO LOG HAY CHUA =======================
    def is_exist_in(self, id_card_check):
        try:
            check = self.entry_logs.find_one({"id_card": id_card_check})
            if check:
                return True
            return False
        except Exception as e:
            with open(entrylog_file,'r',encoding='utf-8') as f:
                data_log=json.load(f)
            for data in data_log:
                if data["id_card"]==id_card_check:
                    return True
            logging.error("OFFLINE CHECK EXIST LOG ID: {}".format(id_card_check))
            return False

    # ============= LUU DU LIEU =======================
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
            logging.error("USING OFFLINE DATA: {}".format(traceback.format_exc()))
            return False


    # ============= XE VAO =======================
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
                logging.warning("Xe het han su dung bai: {} ngay".format(expiry * (-1)))
                temp = "WARNING"
                return
            else:
                logging.info("Xe con han su dung bai: {} ngay".format(expiry))

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
                    logging.warning(
                        "Bien so: {}\nLuu du lieu vao khong thanh cong".format(vehicle["license_plate"]))

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
                        logging.warning("OFFLINE SAVE: \nBien so: {}\nLuu du lieu vao khong thanh cong".format(
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
                            if entry.get("id_card") == vehicle.get("id_card")
                               and entry.get("name_parking") == self.NameParking
                               and entry.get("checkin_time")  # đảm bảo có field này
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

    # ============= XE RA =======================
    def checkout_car(self, id_car_check):
        global out_ok
        # try:
        # Kiá»ƒm tra cÃ³ tá»“n táº¡i xe hay chÆ°a
        datetimee = self.MongoDBServer.get_date_time()
        vehicle = self.vehicles.find_one({"id_card": id_car_check, "name_parking": self.NameParking})
        if not vehicle:
            self.save_data(license_plate=None, id_card=id_car_check, checkin_time=None, checkout_time=datetimee,
                           status="ERROR")
            print("Xe khong ton tai trong he thong!")
            return

        # Kiem tra han su dung bai xe
        expiry = self.ModulCheck.is_expiry_available(vehicle["registration_date"], datetime_now=datetimee, months=6)
        temp = "OK"
        if expiry <= timedelta(0):
            print("Xe het han su dung bai: {} ngay".format(expiry * (-1)))
            temp = "WARNING"
        else:
            print("Xe con han su dung bai: {} ngay".format(expiry))
        # Kiem tra xe ra bai
        if vehicle["car_parked"] is True:
            self.insert_checkout(vehicle=vehicle, state=False, checkout_time=datetimee, slot=-1)
            out_ok = "OUTOK"
            print("Bien so: {}\nThoi gian ra:{}".format(vehicle["license_plate"], datetimee))
        else:
            if self.is_exist_in(vehicle["id_card"]) is False:
                self.save_data(id_card=vehicle["id_card"], license_plate=vehicle["license_plate"], state=False,
                               checkin_time=None, checkout_time=datetimee, slot=0, status=temp)
                out_ok = "OUTOK"
                print("WARNING: Bien so: {}\nThoi gian ra:{}".format(vehicle["license_plate"], datetimee))
            else:
                # Tim thơi gian ra gan nhat
                logs = self.entry_logs.find({
                    "id_card": vehicle["id_card"],
                    "name_parking": self.NameParking}).sort({"checkout_time": -1})
                listt = list(logs)
                # print(listt)
                if not bool(listt):
                    return
                log = listt[0]
                if self.ModulCheck.is_time_available(log["checkout_time"], datetimee, minutes=self.checktime_set):
                    self.save_data(id_card=vehicle["id_card"], license_plate=vehicle["license_plate"], state=False,
                                   checkin_time=None, checkout_time=datetimee, slot=0, status=temp)
                    out_ok = "OUTOK"
                    print("WARNING: Bien so: {}\nThoi gian ra:{}".format(vehicle["license_plate"], datetimee))
                else:
                    print("WARNING: Bien so: {}\nKhong trong bÃ£i".format(vehicle["license_plate"]))
                    return
        time = datetimee.strftime("%H:%M:%S")
        date = datetimee.strftime("%Y-%m-%d")
        datetime_str = date + " " + time
        expiry_str = str(expiry.days) + " ngay"

        return vehicle["license_plate"], vehicle["name"], datetime_str, expiry_str, "Ra"
        # except Exception as e:
        #     logging.error("{}".format(traceback.format_exc()))




def thread_checkin(com, baudrate):
    global in_ok, data_send
    id_in_temp = "-1"
    ser_rfid = serial.Serial(port=com, baudrate=baudrate, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                             bytesize=serial.EIGHTBITS, timeout=1)

    reset_second = time.time()
    while True:
        data_bytes = ser_rfid.read(18)
        data = data_bytes[4:-2].hex().upper()
        # data = ser_rfid.readline().decode('utf-8').strip()
        # if len(data) == 24:
        if len(data) > 5:
            if data != id_in_temp:
                on_pin()
                logging.info("ID nhan duoc: {}".format(data))
                checkin = ControlCar(nameparking="A", checktime_set=45)
                checkin.checkin_car(data)
                # if in_ok=="INOK":
                #     data_send="INOK"
                #     in_ok=""
                id_in_temp = data
        if time.time() - reset_second > 3:
            id_in_temp = ""
            reset_second = time.time()
            off_pin()


def thread_checkout(com, baudrate):
    global out_ok, data_send
    id_in_temp = "-1"
    ser_rfid = serial.Serial(port=com, baudrate=baudrate, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                             bytesize=serial.EIGHTBITS, timeout=1)
    reset_second = time.time()
    while True:
        data_bytes = ser_rfid.read(18)
        data = data_bytes[4:-2].hex().upper()
        # data = ser_rfid.readline().decode('utf-8').strip()
        if len(data) == 24:
            if data != id_in_temp:
                print(" ")
                print("ID ra nhAN: ", data)
                logging.info("ID ra nhan: {}".format(data))
                checkout = ControlCar(nameparking="A", checktime_set=3)
                checkout.checkout_car(data)
                id_in_temp = data
        if time.time() - reset_second > 5:
            id_in_temp = ""
            reset_second = time.time()


def main():
    # thread_sen = threading.Thread(target=thread_send, args=("/dev/tty1", 9600))
    # thread_sen.start()
    thread = threading.Thread(target=thread_checkin, args=(port_name, baudrate))
    # thread = threading.Thread(target=thread_checkin, args=("COM1", 9600))
    thread.start()
    # threadd = threading.Thread(target=thread_checkout, args=("/dev/tty3", 9600))
    # threadd.start()





if __name__ == '__main__':
    # main_oneway("/dev/ttyUSB0", 57600)
    main()

# SEVT_Parking_In
## Tạo service
```
sudo nano /etc/systemd/system/myapp.service

## Nội dung file myapp.service
```
[Unit]
Description=My Python Script Service


[Service]
StandardOutput=journal
StandardError=journal
User=meg
WorkingDirectory=/home/meg/SEVT_Parking_In
ExecStart=/home/meg/myenv/bin/python /home/meg/SEVT_Parking_In/Checkin_MODE.py
Restart=always    
RestartSec=4
StartLimitIntervalSec=0
[Install]
WantedBy=multi-user.target

## Lưu lại
```
sudo systemctl daemon-reload          # Nạp lại danh sách service
sudo systemctl enable myapp # Tự chạy khi boot
sudo systemctl start myapp  # Chạy ngay


# SEVT_Parking_In
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


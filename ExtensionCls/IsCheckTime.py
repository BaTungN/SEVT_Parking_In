from datetime import timezone, timedelta, timedelta 
from datetime import datetime
from dateutil.relativedelta import relativedelta
class IsCheckTime:
    def __init__(self, nameparking):
        self.NameParking = nameparking

    #Kiem tra thoi gian ke tiep xe duoc vao bai
    def is_time_available(self, datetime_1, datetime_2, years=0, months=0, days=0, hours=0, minutes=0, seconds=0):
        if not isinstance(datetime_1, datetime):
            datetime_1 = datetime.fromisoformat(datetime_1)
        if not isinstance(datetime_2, datetime):
            datetime_2 = datetime.fromisoformat(datetime_2)
        delta_time = relativedelta(years=years, months=months, days=days, hours=hours, minutes=minutes, seconds=seconds)
        datetime1 = datetime_1 + delta_time
        datetime2 = datetime_2
        return datetime1 < datetime2
    # Kiem tra thoi han dang ky

    def is_expiry_available(self, datetime_registration, datetime_now,
                            years=0, months=0, days=0, hours=0, minutes=0, seconds=0):
        if datetime_registration.tzinfo is None:
            datetime_registration = datetime_registration.replace(tzinfo=timezone.utc)
        compare_time = datetime_now - datetime_registration
        experi_state=True
        if compare_time > timedelta(days=0):
            print(f"Con han: {compare_time.days}")
        else:
            print(f"Het han: {-compare_time.days}")
            experi_state=False

        return experi_state,compare_time.days

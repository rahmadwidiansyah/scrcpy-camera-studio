class AndroidDevice:
    def __init__(self, serial, status, model_name):
        self.serial = serial          # Serial number perangkat
        self.status = status          # Status dari adb (device, unauthorized, offline)
        self.model_name = model_name  # Nama model/pasar dari perangkat
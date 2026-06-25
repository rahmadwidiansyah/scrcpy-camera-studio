from services.directory_manager import DirectoryManager
from services.runtime_manager import RuntimeManager

class Config:
    APP_DIR = DirectoryManager.APP_DIR
    DATA_DIR = DirectoryManager.DATA_DIR
    BIN_DIR = DirectoryManager.BIN_DIR
    CACHE_DIR = DirectoryManager.CACHE_DIR
    LOGS_DIR = DirectoryManager.LOGS_DIR
    SETTINGS_DIR = DirectoryManager.SETTINGS_DIR

    @staticmethod
    def check_dependency(name):
        return RuntimeManager.check_dependency(name)

    @staticmethod
    def get_bin_path(name):
        return RuntimeManager.get_bin_path(name)

APP_NAME = "Scrcpy Camera Studio"
APP_NAME_SHORT = "SCS"


class VersionManager:
    CURRENT_VERSION = "3.1.0"
    BUILD_NUMBER = "300"
    RELEASE_CHANNEL = "stable"

    @classmethod
    def get_version_string(cls):
        return f"v{cls.CURRENT_VERSION} (Build {cls.BUILD_NUMBER}) [{cls.RELEASE_CHANNEL}]"


# Backward compatibility
current_version  = VersionManager.CURRENT_VERSION
build_number     = VersionManager.BUILD_NUMBER
release_channel  = VersionManager.RELEASE_CHANNEL

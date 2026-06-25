class VersionManager:
    CURRENT_VERSION = "1.0.0"
    BUILD_NUMBER = "100"
    RELEASE_CHANNEL = "stable"

    @classmethod
    def get_version_string(cls):
        return f"v{cls.CURRENT_VERSION} (Build {cls.BUILD_NUMBER}) [{cls.RELEASE_CHANNEL}]"

# Backward compatibility (agar kode yang mengimpor langsung dari module level tetap berjalan)
current_version = VersionManager.CURRENT_VERSION
build_number = VersionManager.BUILD_NUMBER
release_channel = VersionManager.RELEASE_CHANNEL

from dataclasses import dataclass
from typing import Dict, List, Callable, Type, Any
from services.update_service import UpdateCheckResult, InstallPlan
from services.download_manager import DownloadProgress

@dataclass
class CheckStartedEvent:
    pass

@dataclass
class CheckFinishedEvent:
    result: UpdateCheckResult

@dataclass
class UpdateAvailableEvent:
    latest_version: str
    download_url: str
    release_notes: str

@dataclass
class UpdateNotAvailableEvent:
    current_version: str

@dataclass
class DownloadStartedEvent:
    download_url: str

@dataclass
class DownloadProgressEvent:
    progress: DownloadProgress

@dataclass
class DownloadPausedEvent:
    pass

@dataclass
class DownloadResumedEvent:
    pass

@dataclass
class DownloadFinishedEvent:
    zip_path: str

@dataclass
class DownloadFailedEvent:
    error_message: str

@dataclass
class PrepareStartedEvent:
    zip_path: str

@dataclass
class PrepareFinishedEvent:
    extract_dir: str

@dataclass
class InstallReadyEvent:
    plan: InstallPlan


class EventBus:
    def __init__(self):
        self._listeners: Dict[Type[Any], List[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: Type[Any], callback: Callable[[Any], None]):
        """Subscribes a callback to a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        if callback not in self._listeners[event_type]:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: Type[Any], callback: Callable[[Any], None]):
        """Unsubscribes a callback from a specific event type."""
        if event_type in self._listeners and callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)

    def publish(self, event: Any):
        """Publishes an event to all subscribed listeners."""
        event_type = type(event)
        if event_type in self._listeners:
            # Iterate over a copy to prevent issues if a listener unsubscribes during processing
            for callback in list(self._listeners[event_type]):
                try:
                    callback(event)
                except Exception:
                    # Prevent a failing listener from blocking other subscribers
                    pass

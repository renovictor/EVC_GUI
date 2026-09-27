from enum import Enum, auto
import logging
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

class AppState(Enum):
    INITIALIZATION = auto()
    IDLE = auto()
    SCAN_EQUIPMENT = auto()
    CHECK_CONNECTION = auto()
    GETTING_START = auto()
    RUN = auto()
    SAVE_DATA = auto()
    DOWNLOADING_CONTOUR = auto()
    CLEANUP = auto()
    ERROR = auto()
    EXIT = auto()

ALLOWED_TRANSITIONS = {
    AppState.INITIALIZATION: {AppState.IDLE, AppState.ERROR},
    AppState.IDLE: {AppState.SCAN_EQUIPMENT, AppState.DOWNLOADING_CONTOUR, AppState.CLEANUP, AppState.EXIT},
    AppState.SCAN_EQUIPMENT: {AppState.CHECK_CONNECTION, AppState.IDLE, AppState.ERROR},
    AppState.CHECK_CONNECTION: {AppState.GETTING_START, AppState.IDLE, AppState.ERROR},
    AppState.GETTING_START: {AppState.RUN, AppState.IDLE, AppState.ERROR},
    AppState.RUN: {AppState.SAVE_DATA, AppState.IDLE, AppState.ERROR},
    AppState.SAVE_DATA: {AppState.RUN, AppState.IDLE, AppState.ERROR},
    AppState.DOWNLOADING_CONTOUR: {AppState.IDLE, AppState.ERROR},
    AppState.ERROR: {AppState.IDLE, AppState.CLEANUP},
    AppState.CLEANUP: {AppState.IDLE, AppState.EXIT},
    AppState.EXIT: set(),
}

class EvcStateMachine(QObject):
    state_changed = Signal(object, object, str)
    transition_rejected = Signal(object, object, str)

    def __init__(self):
        super().__init__()
        self._state = AppState.INITIALIZATION

    @property
    def state(self):
        return self._state

    def transition(self, target: AppState, reason: str = "") -> bool:
        source = self._state
        if target not in ALLOWED_TRANSITIONS[source]:
            log.warning("Rejected transition %s -> %s: %s", source.name, target.name, reason)
            self.transition_rejected.emit(source, target, reason)
            return False
        self._state = target
        log.info("State transition %s -> %s: %s", source.name, target.name, reason)
        self.state_changed.emit(source, target, reason)
        return True

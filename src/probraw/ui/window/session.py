from __future__ import annotations

from .session_paths import SessionPathsMixin
from .session_development import SessionDevelopmentMixin
from .session_state import SessionStateMixin
from .session_queue import SessionQueueMixin


class SessionWorkflowMixin(
    SessionPathsMixin,
    SessionDevelopmentMixin,
    SessionStateMixin,
    SessionQueueMixin,
):
    pass

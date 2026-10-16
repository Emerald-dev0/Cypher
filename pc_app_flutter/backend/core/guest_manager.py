"""
Guest Session Management Module
Handles temporary guest access to PC files with expiry and folder restrictions.
"""

import secrets
import threading
from datetime import datetime, timedelta

class GuestSession:
    """Represents a single guest access session."""
    
    def __init__(self, token: str, allowed_folders: list[str], duration_minutes: int, host_device_id: str):
        self.token = token
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(minutes=duration_minutes)
        self.allowed_folders = allowed_folders
        self.host_device_id = host_device_id
        self.access_count = 0
        # Every entry is {"timestamp": str, "file_path": str, "action": str} —
        # annotated because `[]` alone leaves mypy unable to infer the element
        # type, and because the bound in log_access() depends on it being a list.
        self.access_log: list[dict[str, str]] = []
        self.is_active = True
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now() > self.expires_at
    
    def extend(self, additional_minutes: int):
        """Extend session expiry."""
        self.expires_at += timedelta(minutes=additional_minutes)
    
    # Bound the in-memory log. to_dict() already sliced the tail for serialisation,
    # but the underlying list grew without limit — so a guest requesting files in a
    # loop could grow node memory indefinitely for the lifetime of the session.
    # access_count still records the true total.
    MAX_LOG_ENTRIES = 200

    def log_access(self, file_path: str, action: str):
        """Log a file access event."""
        self.access_count += 1
        self.access_log.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_path": file_path,
            "action": action
        })
        if len(self.access_log) > self.MAX_LOG_ENTRIES:
            del self.access_log[:len(self.access_log) - self.MAX_LOG_ENTRIES]
    
    def to_dict(self):
        """Serialize session to dictionary."""
        return {
            "token": self.token,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": self.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "allowed_folders": self.allowed_folders,
            "access_count": self.access_count,
            "access_log": self.access_log[-5:], # Latest 5 actions
            "is_active": self.is_active,
            "time_remaining_seconds": max(0, int((self.expires_at - datetime.now()).total_seconds()))
        }


class GuestSessionManager:
    """Manages all active guest sessions."""
    
    def __init__(self):
        self.sessions: dict[str, GuestSession] = {}
        self.lock = threading.Lock()
        self._start_cleanup_thread()
    
    def create_session(self, allowed_folders: list[str], duration_minutes: int, host_device_id: str) -> str:
        """
        Create a new guest session.
        
        Args:
            allowed_folders: List of folder paths guest can access
            duration_minutes: Session duration in minutes
            host_device_id: ID of the host device creating the session
        
        Returns:
            Guest token string
        """
        token = secrets.token_urlsafe(32)
        
        with self.lock:
            self.sessions[token] = GuestSession(
                token=token,
                allowed_folders=allowed_folders,
                duration_minutes=duration_minutes,
                host_device_id=host_device_id
            )
        
        return token
    
    def validate_token(self, token: str) -> GuestSession | None:
        """
        Validate a guest token and return session if valid.
        
        Returns:
            GuestSession if valid and not expired, None otherwise
        """
        with self.lock:
            if token not in self.sessions:
                return None

            session = self.sessions[token]

            # SECURITY FIX (audit follow-up): revocation was a no-op.
            #
            # end_session() set is_active = False, but this method only checked
            # is_expired(). So /guest/end returned {"success": true}, the desktop
            # Security tab dropped the session from its list (get_all_active_sessions
            # *does* filter on is_active), and the guest kept full file access until
            # the natural expiry — up to hours later.
            #
            # That is the worst possible failure shape: the host believes a third
            # party has been cut off, the UI confirms it, and they have not been.
            if not session.is_active:
                return None

            if session.is_expired():
                session.is_active = False
                return None

            return session
    
    def get_session(self, token: str) -> GuestSession | None:
        """Get session without validation (for debugging/monitoring)."""
        with self.lock:
            return self.sessions.get(token)
    
    def end_session(self, token: str) -> bool:
        """End a guest session immediately."""
        with self.lock:
            if token in self.sessions:
                self.sessions[token].is_active = False
                return True
        return False
    
    def extend_session(self, token: str, additional_minutes: int) -> bool:
        """Extend session duration."""
        session = self.validate_token(token)
        if session:
            with self.lock:
                session.extend(additional_minutes)
            return True
        return False
    
    def get_all_active_sessions(
        self, host_device_id: str | None = None
    ) -> list[dict]:
        # `host_device_id: str = None` was an implicit Optional — PEP 484 forbids
        # it and mypy flags it, because the annotation claimed a value the default
        # contradicted. None means "do not filter", which is what the body does.
        """Get all active guest sessions, optionally filtered by host device."""
        with self.lock:
            sessions = []
            for _token, session in self.sessions.items():
                if not session.is_expired() and session.is_active:
                    if host_device_id is None or session.host_device_id == host_device_id:
                        sessions.append(session.to_dict())
            return sessions
    
    def log_guest_access(self, token: str, file_path: str, action: str):
        """Log a guest file access."""
        session = self.validate_token(token)
        if session:
            with self.lock:
                session.log_access(file_path, action)
    
    def _cleanup_expired_sessions(self):
        """Periodically remove expired sessions."""
        import time
        while True:
            time.sleep(60)  # Clean every minute
            with self.lock:
                expired_tokens = [
                    token for token, session in self.sessions.items()
                    if session.is_expired()
                ]
                for token in expired_tokens:
                    del self.sessions[token]
    
    def _start_cleanup_thread(self):
        """Start background cleanup thread."""
        thread = threading.Thread(target=self._cleanup_expired_sessions, daemon=True)
        thread.start()


# Global instance
guest_manager = GuestSessionManager()

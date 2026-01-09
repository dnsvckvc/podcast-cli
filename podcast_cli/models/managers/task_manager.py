import time
import threading

from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from models.downloaders.yt_downloader import YTDownloader
from models.downloaders.rss_feed_downloader import RSS_Feed_Downloader
from models.transcribers.salad_transcriber import SaladTranscriber
from models.transcribers.whisper_transcriber import WhisperTranscriber
from models.summarizers.openai_summarizer import OpenAI_Summarizer


class TaskStatus(Enum):
    FAILED = "failed"
    PENDING = "pending"
    COMPLETED = "completed"
    DOWNLOADING = "downloading"
    SUMMARIZING = "summarizing"
    TRANSCRIBING = "transcribing"


@dataclass
class TaskInfo:
    task_id: str
    user_id: str
    status: TaskStatus
    progress: float = 0.0
    message: str = ""
    created_at: float = None
    updated_at: float = None
    result: Optional[Dict] = None
    error: Optional[str] = None

    def __post_init__(self):
        now = time.time()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def update(
        self,
        status: TaskStatus = None,
        progress: float = None,
        message: str = None,
        result: Dict = None,
        error: str = None,
    ):
        if status is not None:
            self.status = status
        if progress is not None:
            self.progress = progress
        if message is not None:
            self.message = message
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error
        self.updated_at = time.time()


class UserContext:
    """Holds per-user component instances"""

    def __init__(self, config):
        self.yt_downloader = YTDownloader(config=config["youtube"])
        self.rss_downloader = RSS_Feed_Downloader(config=config["rss_feed"])
        if config.get("transcriber", "salad") == "salad":
            self.transcriber = SaladTranscriber(config=config["salad"])
        else:
            self.transcriber = WhisperTranscriber(config=config["whisper"])
        self.summarizer = OpenAI_Summarizer(config=config["openai"])


class TaskManager:
    def __init__(self, config):
        self.config = config
        self.user_contexts: Dict[str, UserContext] = {}
        self.tasks: Dict[str, Dict[str, TaskInfo]] = {}
        self.lock = threading.RLock()

    def init_user(self, user_id: str):
        with self.lock:
            if user_id not in self.user_contexts:
                self.user_contexts[user_id] = UserContext(self.config)
                self.tasks[user_id] = {}

    def create_task(self, user_id: str, task_id: str) -> TaskInfo:
        """Initialize per-user context and register new task"""
        self.init_user(user_id)
        with self.lock:
            info = TaskInfo(
                task_id=task_id,
                user_id=user_id,
                status=TaskStatus.PENDING,
                message="Task created",
            )
            self.tasks[user_id][task_id] = info
            return info

    def update_task(self, user_id: str, task_id: str, **kwargs) -> Optional[TaskInfo]:
        with self.lock:
            task = self.tasks.get(user_id, {}).get(task_id)
            if task:
                task.update(**kwargs)
                return task
            return None

    def get_task_dict(self, user_id: str, task_id: str) -> Optional[Dict]:
        task = self.tasks.get(user_id, {}).get(task_id)
        if task:
            d = asdict(task)
            d["status"] = task.status.value
            return d
        return None

    def get_user_context(self, user_id: str) -> UserContext:
        self.init_user(user_id)
        return self.user_contexts[user_id]

    def cleanup_old_tasks(self, max_age_hours: int = 48):
        current = time.time()
        cutoff = max_age_hours * 3600
        with self.lock:
            for _, tasks in list(self.tasks.items()):
                expired = [
                    tid for tid, t in tasks.items() if current - t.created_at > cutoff
                ]
                for tid in expired:
                    del tasks[tid]

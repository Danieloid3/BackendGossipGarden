import logging
import os
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
import concurrent.futures
from datetime import datetime

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

class FirebaseStorageRotatingHandler(RotatingFileHandler):
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)

    def doRollover(self):
        super().doRollover()
        # After rollover, check if the oldest backup exists
        oldest_backup = f"{self.baseFilename}.{self.backupCount}"
        if os.path.exists(oldest_backup):
            # The maximum number of files has been reached. Trigger batch upload.
            files_to_upload = [f"{self.baseFilename}.{i}" for i in range(1, self.backupCount + 1)]
            _executor.submit(self._upload_batch_to_storage, files_to_upload)

    def _upload_batch_to_storage(self, files):
        try:
            from firebase_admin import storage
            bucket = storage.bucket()
            
            timestamp_folder = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
            
            for file_path in files:
                if os.path.exists(file_path):
                    file_name = os.path.basename(file_path)
                    blob = bucket.blob(f"server_logs/{timestamp_folder}/{file_name}")
                    blob.upload_from_filename(file_path)
                    
                    # Delete the local file after successful upload to free up disk space
                    os.remove(file_path)
        except Exception as e:
            # Silently fail if upload fails, to prevent crash loops
            # Standard error printing (bypasses logger to avoid infinite loops)
            print(f"Error uploading logs to Firebase Storage: {e}")


def setup_logging():
    # Ensure logs directory exists
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "gossip_garden.log")

    # Formatter for file (clean text with timestamp)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Custom Rotating File Handler that uploads to Firebase Storage (10 MB per file, keep 5)
    file_handler = FirebaseStorageRotatingHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(file_formatter)

    # Rich Console Handler (for development readability)
    console_handler = RichHandler(rich_tracebacks=True, markup=True)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(message)s", datefmt="[%X]")
    console_handler.setFormatter(console_formatter)

    # Configure the root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler]
    )

    # Suppress over-talkative third party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("firebase_admin").setLevel(logging.WARNING)
    
    logger = logging.getLogger("gossip_garden")
    logger.info("Logging system initialized (Firebase Storage Batch mode active).")
    return logger

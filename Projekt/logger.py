
import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file_path = os.path.join(LOG_DIR, "system.log")

logger = logging.getLogger("RPSLogger")
logger.setLevel(logging.DEBUG)  # DEBUG pre vývoj, INFO pre produkciu

# Rotujúci file handler
file_handler = RotatingFileHandler(log_file_path, maxBytes=5_000_000, backupCount=3)
file_handler.setLevel(logging.DEBUG)

# Formát logovania
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
file_handler.setFormatter(formatter)

# Pripojenie handlera
logger.addHandler(file_handler)

# Konzolový výstup (voliteľné počas vývoja)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

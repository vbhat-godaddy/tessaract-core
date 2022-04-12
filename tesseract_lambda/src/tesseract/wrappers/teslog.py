import logging
import random
import time
from datetime import datetime

import boto3

from tesseract.wrappers.wrapper_config import CODE_BUCKET, TESSERACT_LOG


class Teslog:
    io_log_obj = None

    def __init__(self, io_log_obj):
        self.logger = logging.getLogger("Tesseract")
        print(self.logger)
        formatter = logging.Formatter(
            "[%(filename)s:%(lineno)s - %(funcName)s()] %(message)s"
        )
        self.logger.setLevel(logging.DEBUG)
        # 1. adding steam handler to display logs on console
        io_log_handler = logging.StreamHandler()
        io_log_handler.setFormatter(formatter)
        self.logger.addHandler(io_log_handler)
        # 2. Initialize stream handler with an io buffer
        string_io_log_handler = logging.StreamHandler(io_log_obj)
        string_io_log_handler.setFormatter(formatter)
        self.logger.addHandler(string_io_log_handler)
        self.io_log_obj = io_log_obj

    def get_logger(self):
        return self.logger

    def upload_logs(self):
        log_suffix = datetime.fromtimestamp(time.time()).strftime("%Y/%m-%d/%H/%M%S-")
        random_no = random.randrange(10, 99, 1)
        log_path = TESSERACT_LOG + str(log_suffix) + str(random_no) + ".log"
        s3_client = boto3.client("s3")
        try:
            resp = s3_client.put_object(
                Body=self.io_log_obj.getvalue(), Bucket=CODE_BUCKET, Key=log_path
            )
            self.logger.info(resp)
        except BaseException as e:
            self.logger.error("TesLog: Cannot upload logfile")
            self.logger.error(e)

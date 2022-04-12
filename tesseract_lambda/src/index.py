import logging
from tesseract.wrappers.tesseract_mod import Tesseract

# lambda handler
def handler(event, context):
    tesObj = Tesseract()
    try:
        tesObj.get_insight_execution_list()
    except BaseException as e:
        logging.error("Issue obtaining & processing execution list")
        logging.error(e)
    try:
        tesObj.upload_all_logs()
    except BaseException as e:
        logging.error("Unable to upload execution logs")
        logging.error(e)
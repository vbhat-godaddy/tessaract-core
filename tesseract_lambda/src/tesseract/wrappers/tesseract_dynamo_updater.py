import gzip
import json
import logging

import boto3


def tesdyn_handler(event, context):
    print(event)
    upload_dynamo(
        event["s3_bucket"],
        event["input_file"],
        event["insight_name"],
        event["dynamo_key"],
    )


def upload_dynamo(s3_bucket, prefix, insight_name, dynamo_key):
    s3_resx = boto3.resource("s3")
    obj = s3_resx.Object(s3_bucket, prefix)
    with gzip.GzipFile(fileobj=obj.get()["Body"]) as gzipfile:
        content = gzipfile.read()
    content = content.decode("utf-8")
    content_array = content.split("\n")

    dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
    table = dynamodb_client.Table("tesseract_" + insight_name)

    for res_json_str in content_array:
        if len(res_json_str) < 5:
            continue
        res_json = json.loads(res_json_str)
        try:
            # insight_key = res_json[dynamo_key]
            # res_json["insight_key"] = res_json.pop(dynamo_key)
            table.put_item(
                Item=res_json,
                TableName="tesseract_" + insight_name,
            )
        except dynamodb_client.exceptions.ResourceNotFoundException as rne:
            logging.error("Update Dynamo: Resource Not Found " + str(rne))
        except dynamodb_client.exceptions.TransactionConflictException as te:
            logging.error("Update Dynamo: TransactionConflictException " + str(te))
        except dynamodb_client.exceptions.RequestLimitExceeded as re:
            logging.error("Update Dynamo: RequestLimitExceeded " + str(re))
        except dynamodb_client.exceptions.InternalServerError as se:
            logging.error("Update Dynamo: InternalServerError " + str(se))
        except BaseException as e:
            print(e)
            logging.error("Update Dynamo: Error uploading item" + str(res_json))


# upload_dynamo(
# "databases/tesseract/test_insight1_json/20220122_115345_00044_yvfjq_e5d4df82-32c7-4b16-b9f9-ad0d4ec42470.gz",
# "test_insight1","country_site_code")

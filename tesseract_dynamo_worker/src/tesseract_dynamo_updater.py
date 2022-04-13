import gzip
import json
import logging
from decimal import Decimal

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
        try:
            res_json = json.loads(res_json_str)
        except BaseException as e:
            print(e)
            logging.error("Bad Json")
            print(res_json_str)
            continue
        try:
            insight_key = res_json[dynamo_key]
            if len(insight_key.strip()) == 0:
                print("faulty json")
                print(res_json_str)
                continue
            res_json = json.loads(json.dumps(res_json), parse_float=Decimal)
            # res_json["insight_key"] = res_json.pop(dynamo_key)
            table.put_item(
                Item=res_json,
                TableName="tesseract_" + insight_name,
            )
        except BaseException as e:
            print(e)
            logging.error("Update Dynamo: Error uploading item" + str(res_json))


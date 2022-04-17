# from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
import datetime
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from random import randrange

import boto3
import botocore
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook

from tesseract.wrappers.tena import Tena
from tesseract.wrappers.tessync import Tessync
from tesseract.wrappers.wrapper_config import (
    ATHENA_RESULTS,
    BASE_S3,
    CODE_BUCKET,
    INSIGHT_DYNAMO,
    INSIGHT_INPUT,
    INSIGHT_NOTIFICATION,
    TES_DYN_WORKER_CNT,
)

# from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

DOCS = """
## This DAG is created as part of self learning/self coding Tesseract module

#### Owner
For data pointers/ concerns, please contact:
[aprasad2@godaddy.com](mailto:aprasad2@godaddy.com).
"""
'''
def slack_failure_notification(context):
    slack_msg = """
                @dsm-oncall
                :red_circle: Dag Failed.
                *Dag*: {dag}
                *Execution Time*: {exec_date}
                *Log Url*: {log_url}
                """.format(
        dag=context.get('task_instance').dag_id,
        exec_date=context.get('execution_date'),
        log_url=context.get('task_instance').log_url,
    )
    failed_alert = SlackWebhookOperator(
        task_id='slack_notification', http_conn_id='serp_slack_webhook_failure', message=slack_msg
    )
    return failed_alert.execute(context=context)
'''


def purge_schema_op(**kwargs):
    insight_name = kwargs["insight"]
    s3_resx = boto3.resource("s3")
    s3_bucket = s3_resx.Bucket(CODE_BUCKET)
    s3_bucket.objects.filter(
        Prefix="databases/tesseract/" + insight_name + "/"
    ).delete()
    purge_query = "DROP TABLE IF EXISTS " + insight_name + " ;"
    print(purge_query)

    tena_object = Tena(logging.getLogger("purge_schema"))
    insight_config = {"name": insight_name, "database": "tesseract"}
    result = tena_object.tena_process(insight_config, purge_query)
    print("Tesseract Helper: Insight purge result = " + str(result))
    logging.info("Tesseract Helper: checksum update result = " + str(result))
    return result


def create_schema_op(**kwargs):
    insight_name = kwargs["insight"]
    s3_resx = boto3.resource("s3")
    create_query = "CREATE TABLE " + insight_name
    try:
        s3Obj = s3_resx.Object(
            CODE_BUCKET, INSIGHT_INPUT + insight_name + "/" + insight_name + ".ddl"
        )
        ddl_content = s3Obj.get()["Body"].read().decode("utf-8")
        print(ddl_content)
        create_query += " ( " + ddl_content
    except Exception as e:
        logging.error("Tesseract Helper: DDL Read failed for " + insight_name)
        logging.error(e)
        return False
    create_query += (
        " ) STORED AS ORC LOCATION 's3://"
        + CODE_BUCKET
        + "/databases/tesseract/"
        + insight_name
        + "'"
    )
    tena_object = Tena(logging.getLogger("create_schema"))
    insight_config = {"name": insight_name, "database": "tesseract"}
    result = tena_object.tena_process(insight_config, create_query)
    print("Tesseract Helper: Insight DDL Creation result = " + str(result))
    logging.info("Tesseract Helper: Insight DDL Creation result = " + str(result))
    return result


def copy_dynamo_op(**kwargs):
    insight_name = kwargs["insight"]
    # insight_name = "test_insight1"
    dynamo_key = kwargs["dynamo_key"]
    s3_resx = boto3.resource("s3")
    s3_bucket = s3_resx.Bucket(CODE_BUCKET)
    event_array = []
    for object_summary in s3_bucket.objects.filter(
        Prefix="databases/tesseract/" + insight_name + "_json/"
    ):
        event_json = {
            "s3_bucket": CODE_BUCKET,
            "insight_name": insight_name,
            "dynamo_key": dynamo_key,
            "input_file": object_summary.key,
        }
        event_array.append(event_json)
    if len(event_array) > 0:
        with ThreadPoolExecutor(max_workers=25) as executor:
            results = executor.map(invoke_tes_dyn_loader, event_array)
            logging.info("Results from thread = " + str(results))


def invoke_tes_dyn_loader(payload):
    config = botocore.config.Config(connect_timeout=900, read_timeout=910, retries={"max_attempts": 0})
    lambda_client = boto3.client("lambda", config=config)
    print(payload)
    function_chooser = randrange(TES_DYN_WORKER_CNT)
    if function_chooser == 0:
        lambda_function = "tesseract-lambda-runner"
    else:
        lambda_function = "tesseract-lambda" + str(function_chooser) + "-runner"
    try:
        response = lambda_client.invoke(
            FunctionName=lambda_function,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
    except BaseException as e:
        print(e)
        raise
    print(response)
    print(response["Payload"].read())


def create_dynamo_data_op(**kwargs):
    insight_name = kwargs["insight"]
    dynamo_key = kwargs["dynamo_key"]
    s3_resx = boto3.resource("s3")
    s3_bucket = s3_resx.Bucket(CODE_BUCKET)
    s3_bucket.objects.filter(
        Prefix="databases/tesseract/" + insight_name + "_json/"
    ).delete()
    purge_query = "DROP TABLE IF EXISTS " + insight_name + "_json ;"
    print(purge_query)
    tena_object = Tena(logging.getLogger("create_dynamo_data"))
    insight_config = {"name": insight_name + "_json", "database": "tesseract"}
    result = tena_object.tena_process(insight_config, purge_query)
    print("Tesseract Helper: Dynamo Insight purge result = " + str(result))
    logging.info("Tesseract Helper: Dynamo Insight purge result = " + str(result))

    bucket_count = 10
    athena_client = boto3.client("athena")
    obj_time = datetime.datetime.now()
    obj_prefix = obj_time.strftime("%Y-%m-%d/%H/")

    output_s3 = BASE_S3 + "/" + ATHENA_RESULTS + "/" + insight_name + "/" + obj_prefix
    query_response = None
    try:
        query_response = athena_client.start_query_execution(
            QueryString="SELECT COUNT(*) AS row_count FROM " + insight_name + ";",
            QueryExecutionContext={"Database": "tesseract"},
            ResultConfiguration={
                "OutputLocation": output_s3,
            },
        )
    except athena_client.exceptions.InternalServerException as se:
        logging.error("Tena: tena_process: Internal Server error (500)" + str(se))
        return False
    except athena_client.exceptions.InvalidRequestException as ir:
        logging.error("Tena: tena_process: Bad Request Submitted (400) " + str(ir))
        return False
    except athena_client.exceptions.TooManyRequestsException as re:
        logging.error("Tena: tena_process: Throttling requests (400) " + str(re))
        return False
    except BaseException as be:
        logging.error("Tena: tena_process: Unknown exception " + str(be))
        return False
    poll_flag = True
    counter = 50
    while poll_flag:
        query_status_resp = athena_client.get_query_execution(
            QueryExecutionId=query_response["QueryExecutionId"]
        )
        status = query_status_resp["QueryExecution"]["Status"]["State"]

        if (status == "FAILED") or (status == "CANCELLED"):
            failure_reason = query_status_resp["QueryExecution"]["Status"][
                "StateChangeReason"
            ]
            logging.error("Update Dynamo failed :: " + str(failure_reason))
            poll_flag = False
            break
        elif status == "SUCCEEDED":
            poll_flag = False
            response_query_result = athena_client.get_query_results(
                QueryExecutionId=query_response["QueryExecutionId"]
            )
            result_data = response_query_result["ResultSet"]

            if len(response_query_result["ResultSet"]["Rows"]) > 1:
                header = result_data["Rows"][0]
                rows = result_data["Rows"][1:]
                header = [obj["VarCharValue"] for obj in header["Data"]]
                result = [dict(zip(header, get_row_data(row))) for row in rows]
                print(result)
                row_count = int(result[0]["row_count"])
                bucket_count = (int)(row_count / 70000) + 1
                print("Bucket Count = " + str(bucket_count))
        else:
            counter = counter - 1
            if counter == 0:
                poll_flag = False
                break
            time.sleep(5)
    create_query = "CREATE TABLE " + insight_name + "_json"
    create_query += (
        " WITH ( format = 'JSON', bucketed_by = ARRAY['"
        + dynamo_key
        + "'], bucket_count = "
        + str(bucket_count)
        + ", external_location='s3://"
        + CODE_BUCKET
        + "/databases/tesseract/"
        + insight_name
        + "_json/') "
    )
    create_query += " AS SELECT * FROM " + insight_name + ";"
    tena_object = Tena(logging.getLogger("create_dynamo_data"))
    insight_config = {"name": insight_name + "_json", "database": "tesseract"}
    result = tena_object.tena_process(insight_config, create_query)
    print("Tesseract Helper: Dynamo Insight JSON Creation result = " + str(result))
    logging.info(
        "Tesseract Helper: Dynamo Insight JSON Creation result = " + str(result)
    )
    return result


def get_row_data(data):
    return [obj["VarCharValue"] for obj in data["Data"]]


def create_emr_insight_op(**kwargs):
    insight_name = kwargs["insight"]
    s3_resx = boto3.resource("s3")
    create_query = "INSERT INTO tesseract." + insight_name
    try:
        s3Obj = s3_resx.Object(
            CODE_BUCKET, INSIGHT_INPUT + insight_name + "/" + insight_name + ".hql"
        )
        hql_content = s3Obj.get()["Body"].read().decode("utf-8")
        hql_content = hql_content.replace("\t", " ")
        print(hql_content)
        create_query += "  " + hql_content
    except BaseException as e:
        logging.error("Tesseract Helper: Execution failed for " + insight_name)
        logging.error(e)
        raise
    try:
        print("Uploading Processed insight to S3....")
        logging.info(
            "Tesseract Helper: create_emr_insight_op: Uploading Processed insight to S3"
        )
        s3_resx.Object(
            CODE_BUCKET, INSIGHT_INPUT + insight_name + "/" + insight_name + "_emr.hql"
        ).put(Body=create_query)
    except BaseException as e:
        logging.error("Tesseract Helper: create_emr_insight_op: failed " + insight_name)
        logging.error(e)
        raise


def create_insight_op(**kwargs):
    insight_name = kwargs["insight"]
    s3_resx = boto3.resource("s3")
    create_query = "INSERT INTO " + insight_name
    try:
        s3Obj = s3_resx.Object(
            CODE_BUCKET, INSIGHT_INPUT + insight_name + "/" + insight_name + ".hql"
        )
        hql_content = s3Obj.get()["Body"].read().decode("utf-8")
        print(hql_content)
        create_query += "  " + hql_content
    except BaseException as e:
        logging.error("Tesseract Helper: Execution failed for " + insight_name)
        logging.error(e)
        return False
    tena_object = Tena(logging.getLogger("create_insight"))
    insight_config = {"name": insight_name, "database": "tesseract"}
    print(create_query)
    result = tena_object.tena_process(insight_config, create_query)
    print("Tesseract Helper: Insight Execution result = " + str(result))
    logging.info("Tesseract Helper: Insight Execution result = " + str(result))
    return result


def generate_link_op(**kwargs):
    insight_name = kwargs["insight"]
    tena_object = Tena(logging.getLogger("generate_link"))
    query = "SELECT * FROM tesseract." + insight_name
    return tena_object.generate_link(insight_name, query)


def create_dynamo_op(**kwargs):
    insight_name = "tesseract_" + kwargs["insight"]
    dynamo_key = kwargs["dynamo_key"]
    # insight_name = "tesseract_test_insight1"
    dynamodb_client = AwsBaseHook(
        aws_conn_id="tesseract_aws_conn", client_type="dynamodb"
    ).get_client_type("dynamodb")
    table = dynamodb_client.create_table(
        TableName=insight_name,
        KeySchema=[{"AttributeName": dynamo_key, "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": dynamo_key, "AttributeType": "S"}],
    )
    print(table)
    logging.info("create_dynamo_op: table creation result:")
    logging.info(table)


def delete_dynamo_op(**kwargs):
    insight_name = "tesseract_" + kwargs["insight"]
    # insight_name = "tesseract_test_insight1"
    # dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
    dynamodb_client = boto3.client("dynamodb", region_name="us-west-2")
    print("listing tables")
    print("Insight = " + insight_name)
    existing_tables = dynamodb_client.list_tables()
    print(existing_tables)
    if insight_name in existing_tables["TableNames"]:
        dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
        table = dynamodb_client.Table(insight_name)
        table.delete()
        print("Delete Op issued, now waiting for it to be deleted completely!")
        table.wait_until_not_exists()
    print("delete_dynamo_op: Deletion successful")


def mark_processed_dynamo_op(**kwargs):
    insight_name = kwargs["insight"]
    dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
    table = dynamodb_client.Table(INSIGHT_DYNAMO)
    base = " "
    try:
        response = table.get_item(Key={"insight": insight_name})
        base = response["Item"]["status"]
        print(base)
    except BaseException as e:
        logging.info(
            "mark_processed_dynamo_op: get_item response for "
            + str(insight_name)
            + " "
            + str(e)
        )
    new_base = base.replace("PROCESSING,", "")
    response = table.put_item(
        Item={
            "insight": insight_name,
            "status": str(new_base),
        },
        TableName=INSIGHT_DYNAMO,
    )
    print("Insight marked as processing = " + str(response))
    logging.info("Insight is marked as processsing" + str(response))


def get_dynamo_item_op(insight_name, key):
    dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
    table = dynamodb_client.Table("tesseract_test_insight1")

    response = table.get_item(Key={"insight_key": "ca"})
    print(response["Item"]["insight_value"])


def notify_success_op(**kwargs):
    insight_name = kwargs["insight"]
    file_name = INSIGHT_NOTIFICATION + insight_name + "/_SUCCESS"
    s3_bucket = BASE_S3.strip("s3://")
    s3_resx = boto3.resource("s3")
    s3_resx.Object(s3_bucket, file_name).put(Body="")


def clear_history_op(**kwargs):
    insight_name = kwargs["insight"]
    file_name = INSIGHT_NOTIFICATION + insight_name + "/_SUCCESS"
    s3_bucket = BASE_S3.strip("s3://")
    s3_resx = boto3.resource("s3")
    try:
        s3_resx.Object(s3_bucket, file_name).delete()
    except BaseException as e:
        logging.error("Issue with successfile deletion")
        logging.error(e)


def update_gql_op(**kwargs):
    insight_name = kwargs["insight"]
    insight_key = kwargs["insight_key"]
    storage = kwargs["storage"]
    tessync_client = AwsBaseHook(
        aws_conn_id="tesseract_aws_conn", client_type="appsync"
    ).get_client_type("appsync")
    tsync_obj = Tessync(logging.getLogger("Tessync"), tessync_client)
    deletion_response = tsync_obj.delete_resources(insight_name)
    logging.info("update_gql_op: Sync Deletion Response " + str(deletion_response))
    creation_response = tsync_obj.create_resources(insight_name, storage, insight_key)
    logging.info("update_gql_op: Sync Creation Response " + str(creation_response))

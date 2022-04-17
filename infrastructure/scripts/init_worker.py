import boto3
import botocore
import os
import json
import datetime
import logging
import time


def create_connection():
    config = botocore.config.Config(connect_timeout=900, read_timeout=910, retries={"max_attempts": 0})
    lambda_client = boto3.client("lambda", config=config)
    env_val = os.environ['env_val']
    team_name_val = os.environ['team_name_val']
    secret_id = os.environ['secret_id']
    role = os.environ['role']
    extra_json = {"role_arn": role, "deploy_secret_id": secret_id}
    function_name = "gd-" + team_name_val + "-" + env_val + "-tesseract-connector-runner"
    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps(extra_json),
    )
    print(response)


def initate_tessync():
    client = boto3.client('appsync')
    response = client.list_graphql_apis()
    api_arr = response['graphqlApis']
    api_id = None
    for api_resp in api_arr:
        if api_resp['name'] == "tesseract-sync":
            api_id = api_resp['apiId']
    if api_id != None:
        type_definition = "schema { query: Query }"
        response = client.create_type(
            apiId=api_id, definition=type_definition, format="SDL"
        )
        type_definition += "type Query { randomFunc(): Int }"
        response = client.create_type(
            apiId=api_id, definition=type_definition, format="SDL"
        )
        print(response)


def create_athena_connectors():
    athena_client = boto3.client("athena")
    obj_time = datetime.datetime.now()
    obj_prefix = obj_time.strftime("%Y-%m-%d/%H/")
    env_val = os.environ['env_val']
    team_name_val = os.environ['team_name_val']
    s3_bucket = "gd-" + team_name_val + "-" + env_val + "-tesseract"
    output_s3 = "s3://" + s3_bucket + "/tena_results/setup/" + obj_prefix
    query_arr = []
    vault_string = "CREATE TABLE tesseract.insight_csum_vault (" + \
                   "insight_name string, version string, csum string" + \
                   ") \n STORED AS ORC \n LOCATION '" + \
                   "s3://" + s3_bucket + "/database/tesseract/insight_csum_vault' ;"
    query_arr.append(vault_string)
    csum_string = "CREATE TABLE tesseract.insight_csum_cur (" + \
                  "insight_name string, version string, csum string" + \
                  ") \n STORED AS ORC \n LOCATION '" + \
                  "s3://" + s3_bucket + "/database/tesseract/insight_csum_cur' ;"
    query_arr.append(csum_string)
    runnable_string = "CREATE TABLE tesseract.runnable_insights (" + \
                      "insight_name string) \n STORED AS ORC  \n LOCATION '" + \
                      "s3://" + s3_bucket + "/database/tesseract/runnable_insights' ;"
    query_arr.append(runnable_string)
    query_response = None
    try:
        query_response = athena_client.start_query_execution(
            QueryString="CREATE DATABASE IF NOT EXISTS tesseract " +
                        "LOCATION 's3://" + s3_bucket + "/database/' ;",
            ResultConfiguration={
                "OutputLocation": output_s3,
            },
        )
    except athena_client.exceptions.InternalServerException as se:
        logging.error("Internal Server error (500)" + str(se))
        return False
    except athena_client.exceptions.InvalidRequestException as ir:
        logging.error("Bad Request Submitted (400) " + str(ir))
        return False
    except athena_client.exceptions.TooManyRequestsException as re:
        logging.error("Throttling requests (400) " + str(re))
        return False
    except BaseException as be:
        logging.error("Unknown exception " + str(be))
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
        else:
            counter = counter - 1
            if counter == 0:
                poll_flag = False
                break
            time.sleep(5)
    for query in query_arr:
        execute_query(query, output_s3)


def execute_query(query, output_s3):
    athena_client = boto3.client("athena")
    try:
        query_response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": "tesseract"},
            ResultConfiguration={
                "OutputLocation": output_s3,
            },
        )
    except athena_client.exceptions.InternalServerException as se:
        logging.error("Internal Server error (500)" + str(se))
        return False
    except athena_client.exceptions.InvalidRequestException as ir:
        logging.error("Bad Request Submitted (400) " + str(ir))
        return False
    except athena_client.exceptions.TooManyRequestsException as re:
        logging.error("Throttling requests (400) " + str(re))
        return False
    except BaseException as be:
        logging.error("Unknown exception " + str(be))
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
        else:
            counter = counter - 1
            if counter == 0:
                poll_flag = False
                break
            time.sleep(5)


create_connection()
initate_tessync()
create_athena_connectors()
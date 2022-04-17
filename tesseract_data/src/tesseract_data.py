import datetime
import logging
import time
import boto3


def tesdata_handler(event, context):
    athena_client = boto3.client("athena")
    obj_time = datetime.datetime.now()
    obj_prefix = obj_time.strftime("%Y-%m-%d/%H/")
    ssm = boto3.client('ssm')
    env_val_dict = ssm.get_parameter(Name='/AdminParams/Team/Environment')
    env_val = env_val_dict['Parameter']['Value']
    team_val_dict = ssm.get_parameter(Name='/AdminParams/Team/Name')
    team_val = team_val_dict['Parameter']['Value']
    s3_bucket = "gd-" + team_val + "-" + env_val + "-tesseract"
    output_s3 = "s3://" + s3_bucket + "/tena_results/setup/" + obj_prefix
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


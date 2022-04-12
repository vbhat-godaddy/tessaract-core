"""
Tesseract-Athena (TeNa) is a wrapper that reads in the query feed,
submits the request to AWS Athena to generate required insights.
"""
import datetime
import json
import time

import boto3

from tesseract.wrappers.wrapper_config import ATHENA_RESULTS, BASE_S3, CALLBACK_TOPIC

# logging.basicConfig(level=logging.INFO)


class Tena:
    # constructor

    def __init__(self, logger):
        self.logger = logger
        print("Constructor")

    def tena_process(self, insight_config, insight_query):
        athena_client = boto3.client("athena")
        obj_time = datetime.datetime.now()
        obj_prefix = obj_time.strftime("%Y-%m-%d/%H/")
        insight_name = insight_config["name"]
        database_name = insight_config["database"]
        output_s3 = (
            BASE_S3 + "/" + ATHENA_RESULTS + "/" + insight_name + "/" + obj_prefix
        )
        execution_identifier = ""

        # initiate query
        self.logger.info(
            "Tena: tena_process: Starting query execution for " + str(insight_name)
        )
        try:
            query_response = athena_client.start_query_execution(
                QueryString=insight_query,
                QueryExecutionContext={"Database": database_name},
                ResultConfiguration={
                    "OutputLocation": output_s3,
                },
            )
            execution_identifier = query_response["QueryExecutionId"]
        except athena_client.exceptions.InternalServerException as se:
            self.logger.error(
                "Tena: tena_process: Internal Server error (500)" + str(se)
            )
            return False
        except athena_client.exceptions.InvalidRequestException as ir:
            self.logger.error(
                "Tena: tena_process: Bad Request Submitted (400) " + str(ir)
            )
            return False
        except athena_client.exceptions.TooManyRequestsException as re:
            self.logger.error(
                "Tena: tena_process: Throttling requests (400) " + str(re)
            )
            return False
        except BaseException as be:
            self.logger.error("Tena: tena_process: Unknown exception " + str(be))
            self.send_sns_failure({"insight_name": insight_name})
            return False

        return self.poll_and_notify(execution_identifier, athena_client, insight_name)

    def poll_and_notify(self, execution_identifier, athena_client, insight_name):
        poll_flag = True
        while poll_flag:
            response = None
            try:
                query_status_response = athena_client.get_query_execution(
                    QueryExecutionId=execution_identifier
                )
                query_status = query_status_response["QueryExecution"]["Status"][
                    "State"
                ]
            except athena_client.exceptions.InternalServerException as se:
                self.logger.error(
                    "Tena: poll_and_notify: Internal Server error (500)" + str(se)
                )
                return False
            except athena_client.exceptions.InvalidRequestException as ir:
                self.logger.error(
                    "Tena: poll_and_notify: Bad Request Submitted (400) " + str(ir)
                )
                return False
            except BaseException as be:
                self.logger.error("Tena: poll_and_notify: Unknown exception " + str(be))
                return False

            if (query_status == "FAILED") or (query_status == "CANCELLED"):
                log_json = {
                    "insight_name": insight_name,
                    "execution_id": execution_identifier,
                }
                self.send_sns_failure(log_json)
                return False
            elif query_status == "SUCCEEDED":
                log_json = {
                    "insight_name": insight_name,
                    "execution_id": execution_identifier,
                }
                self.send_sns_success(log_json)
                return True
            else:
                response = execution_identifier
            if response is None:
                poll_flag = False
            time.sleep(5)
        return False

    def generate_link(self, insight_name, query):
        athena_client = boto3.client("athena")
        query_ids = []
        try:
            get_named_query_ids = athena_client.list_named_queries()
            query_ids.extend(get_named_query_ids["NamedQueryIds"])
            while "NextToken" in get_named_query_ids:
                get_named_query_ids = athena_client.list_named_queries(
                    NextToken=get_named_query_ids["NextToken"]
                )
                query_ids.extend(get_named_query_ids["NamedQueryIds"])
        except athena_client.exceptions.InternalServerException as se:
            self.logger.error(
                "Tena: generate_link: Internal Server error (500)" + str(se)
            )
            return None
        except athena_client.exceptions.InvalidRequestException as ir:
            self.logger.error(
                "Tena: generate_link: Bad Request Submitted (400) " + str(ir)
            )
            return None
        except BaseException as be:
            self.logger.error("Tena: generate_link: Unknown exception " + str(be))
            return None

        try:
            for _id in query_ids:
                query_response = athena_client.get_named_query(NamedQueryId=_id)
                if (
                    "NamedQuery" in query_response
                    and "Name" in query_response["NamedQuery"]
                ):
                    if (
                        query_response["NamedQuery"]["Name"]
                        == "tesseract_" + insight_name
                    ):
                        print("Deleting Saved Query " + _id)
                        response = athena_client.delete_named_query(NamedQueryId=_id)
                        print(response)
        except athena_client.exceptions.InternalServerException as se:
            self.logger.error(
                "Tena: generate_link: Internal Server error (500)" + str(se)
            )
            return None
        except athena_client.exceptions.InvalidRequestException as ir:
            self.logger.error(
                "Tena: generate_link: Bad Request Submitted (400) " + str(ir)
            )
            return None
        except BaseException as be:
            self.logger.error("Tena: generate_link: Unknown exception " + str(be))
            return None

        try:
            named_query_response = athena_client.create_named_query(
                Name="tesseract_" + insight_name,
                Description="Auto Saved by Tesseract for " + insight_name,
                Database="tesseract",
                QueryString=query,
            )
            print(named_query_response)
            return (
                "https://us-west-2.console.aws.amazon.com/athena/home?"
                "region=us-west-2#:~:text=tesseract_" + insight_name
            )
        except athena_client.exceptions.InternalServerException as se:
            self.logger.error(
                "Tena: generate_link: Internal Server error (500)" + str(se)
            )
            return None
        except athena_client.exceptions.InvalidRequestException as ir:
            self.logger.error(
                "Tena: generate_link: Bad Request Submitted (400) " + str(ir)
            )
            return None
        except BaseException as be:
            self.logger.error("Tena: generate_link: Unknown exception " + str(be))
            return None

    def send_sns_failure(self, response):
        sns_client = boto3.client("sns")
        sns_response = None
        try:
            sns_response = sns_client.publish(
                TargetArn=CALLBACK_TOPIC,
                Message=json.dumps({"default": json.dumps(response)}),
                Subject="FAILURE",
                MessageStructure="json",
            )
        except sns_client.exceptions.NotFoundException as ne:
            self.logger.error(
                "Tena: sns_send_failure: SNS topic not found error " + str(ne)
            )
            return sns_response
        except sns_client.exceptions.InternalErrorException as ie:
            self.logger.error("Tena: sns_send_failure: Internal error " + str(ie))
            return sns_response
        except sns_client.exceptions.InvalidParameterValueException as iv:
            self.logger.error("Tena: sns_send_failure: Invalid Parameter " + str(iv))
            return sns_response
        except sns_client.exceptions.InvalidParameterException as ip:
            self.logger.error("Tena: sns_send_failure: Invalid Parameter " + str(ip))
            return sns_response
        except BaseException as be:
            self.logger.error("Tena: sns_send_failure: Unknown exception " + str(be))
            return sns_response
        return sns_response

    def send_sns_success(self, response):
        sns_client = boto3.client("sns")
        sns_response = None
        try:
            sns_response = sns_client.publish(
                TargetArn=CALLBACK_TOPIC,
                Message=json.dumps({"default": json.dumps(response)}),
                Subject="SUCCEEDED",
                MessageStructure="json",
            )
        except sns_client.exceptions.NotFoundException as ne:
            self.logger.error(
                "Tena: send_sns_success: SNS topic not found error " + str(ne)
            )
            return sns_response
        except sns_client.exceptions.InternalErrorException as ie:
            self.logger.error("Tena: send_sns_success: Internal error " + str(ie))
            return sns_response
        except sns_client.exceptions.InvalidParameterValueException as iv:
            self.logger.error("Tena: send_sns_success: Invalid Parameter " + str(iv))
            return sns_response
        except sns_client.exceptions.InvalidParameterException as ip:
            self.logger.error("Tena: send_sns_success: Invalid Parameter " + str(ip))
            return sns_response
        except BaseException as be:
            self.logger.error("Tena: send_sns_success: Unknown exception " + str(be))
            return sns_response
        return sns_response

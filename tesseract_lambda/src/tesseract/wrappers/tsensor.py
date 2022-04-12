"""
Tesseract-Sensor (TSensor) is a wrapper that checks S3 bucket
for any new/rerun insights and updates it to runnable table
"""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

from tesseract.wrappers.tena import Tena
from tesseract.wrappers.wrapper_config import (
    BASE_S3,
    CODE_BUCKET,
    CURRENT_CSUM,
    INSIGHT_DYNAMO,
    INSIGHT_INPUT,
    INSIGHT_TABLE,
    VAULT_CSUM,
)
import traceback


class TSensor:
    # constructor
    insights_list = []
    insights_values = []

    def __init__(self, logger):
        self.logger = logger
        self.logger.info("TSensor: initiated")
        self.insights_list = []

    def get_all_insights(self):
        s3_client = boto3.client("s3")
        try:
            insight_precursor = s3_client.list_objects_v2(
                Bucket=CODE_BUCKET, Prefix=INSIGHT_INPUT, Delimiter="/"
            )
            for insights in insight_precursor.get("CommonPrefixes", []):
                self.insights_list.append(
                    insights.get("Prefix").replace(INSIGHT_INPUT, "")
                )
        except s3_client.exceptions.NoSuchBucket as nb:
            self.logger.error(
                "TSensor: get_all_insights: No bucket found " + CODE_BUCKET
            )
            self.logger.error("TSensor: get_all_insights: " + str(nb))
            return False
        except BaseException as be:
            self.logger.error("TSensor: get_all_insights: Unknown Error " + str(be))
            return False
        print("Sensor Module: Insights currently present in the system ---- ")
        print(self.insights_list)
        self.logger.info(
            "TSensor: get_all_insights: Insights currently present in the system"
        )
        self.logger.info(str(self.insights_list))
        results = []
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = executor.map(self.update_checksum, self.insights_list)
        except BaseException as be:
            self.logger.error(
                "TSensor: get_all_insights: Error with ThreadPoolExecutor " + str(be)
            )
            return False
        self.logger.info("TSensor: get_all_insights: Concurrent processing results")
        for result in results:
            self.logger.info(result)
        print("Sensor Module: Calculating Checksum...")
        checksum_query = (
            "INSERT INTO "
            + CURRENT_CSUM
            + " VALUES "
            + (",".join(self.insights_values) + ";")
        )
        print(checksum_query)
        self.clear_table(CURRENT_CSUM)
        tena_object = Tena(self.logger)
        insight_config = {"name": "tsensor_current_csum", "database": "tesseract"}
        result = tena_object.tena_process(insight_config, checksum_query)
        print("TSensor: checksum update result = " + str(result))
        self.logger.info("TSensor: checksum update result = " + str(result))

    def get_runnable_insights(self):
        insight_query_result = False
        self.get_all_insights()
        self.clear_table(INSIGHT_TABLE)
        tena_object = Tena(self.logger)
        insight_config = {"name": "tsensor_runnable_insights", "database": "tesseract"}
        runnable_query = (
            "INSERT INTO "
            + INSIGHT_TABLE
            + " SELECT insight_name FROM "
            + CURRENT_CSUM
            + " WHERE insight_name NOT IN (SELECT A.insight_name FROM "
            + CURRENT_CSUM
            + " A JOIN "
            + VAULT_CSUM
            + " B ON A.insight_name=B.insight_name AND A.version=B.version AND A.csum=B.csum);"
        )
        result = tena_object.tena_process(insight_config
                                          , runnable_query)
        insight_query_result = result
        self.logger.info("TSensor: Runnable insights result = " + str(result))
        if insight_query_result is False:
            self.logger.error(
                "TSensor: get_runnable_insights: Issues while getting updated checksum"
            )
            return False
        # update dynamoDB with runnable insights
        self.update_dynamo(INSIGHT_DYNAMO, INSIGHT_TABLE)

        self.clear_table(VAULT_CSUM)
        update_vault_query = (
            "INSERT INTO " + VAULT_CSUM + " SELECT * FROM " + CURRENT_CSUM + ";"
        )
        tena_object = Tena(self.logger)
        insight_config = {"name": "tsensor_vault_upgrade", "database": "tesseract"}
        result = tena_object.tena_process(insight_config, update_vault_query)
        print(result)
        self.logger.info("TSensor: Vault update result = " + str(result))
        return result

    """
    TODO: modularize the following : run_query
    """

    def run_query(self, table, checksum_query):
        self.clear_table(table)
        tena_object = Tena(self.logger)
        insight_config = {"name": "tsensor_current_csum", "database": "tesseract"}
        result = tena_object.tena_process(insight_config, checksum_query)
        print(result)
        self.logger.info("TSensor: checksum update result = " + str(result))
        return result

    def clear_table(self, table):
        s3_resx = boto3.resource("s3")
        s3_bucket = s3_resx.Bucket(CODE_BUCKET)
        s3_bucket.objects.filter(Prefix="databases/tesseract/" + table + "/").delete()
        return None

    def update_dynamo(self, dynamotable, athenatable):
        athena_client = boto3.client("athena")
        query_response = None
        try:
            query_response = athena_client.start_query_execution(
                QueryString="SELECT * FROM " + athenatable,
                QueryExecutionContext={"Database": "tesseract"},
                ResultConfiguration={
                    "OutputLocation": BASE_S3 + "/tensor_dynamo/",
                },
            )
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
            return False
        poll_flag = True
        while poll_flag:
            query_status_resp = athena_client.get_query_execution(
                QueryExecutionId=query_response["QueryExecutionId"]
            )
            status = query_status_resp["QueryExecution"]["Status"]["State"]

            if (status == "FAILED") or (status == "CANCELLED"):
                failure_reason = query_status_resp["QueryExecution"]["Status"][
                    "StateChangeReason"
                ]
                self.logger.error(
                    "TSensor: Update Dynamo failed :: " + str(failure_reason)
                )
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
                    result = [dict(zip(header, self.get_row_data(row))) for row in rows]

                    print(result)

                    dynamodb_client = boto3.resource(
                        "dynamodb", region_name="us-west-2"
                    )
                    table = dynamodb_client.Table(dynamotable)

                    for res_json in result:
                        base = " "
                        try:
                            response = table.get_item(
                                Key={"insight": res_json["insight_name"]}
                            )
                            base = response["Item"]["status"]
                        except BaseException as e:
                            self.logger.info(
                                "TSensor: update_dynamo: get_item response for "
                                + str(res_json["insight_name"])
                                + " "
                                + str(e)
                            )
                        try:
                            response = table.put_item(
                                Item={
                                    "insight": res_json["insight_name"],
                                    "status": "PENDING," + str(base),
                                },
                                TableName=dynamotable,
                            )
                            self.logger.info(
                                "TSensor: update_dynamo: put_item response for "
                                + str(res_json["insight_name"])
                                + " "
                                + str(response)
                            )
                        except dynamodb_client.exceptions.ResourceNotFoundException as rne:
                            self.logger.error(
                                "TSensor: Update Dynamo: Resource Not Found " + str(rne)
                            )
                        except dynamodb_client.exceptions.TransactionConflictException as te:
                            self.logger.error(
                                "TSensor: Update Dynamo: TransactionConflictException "
                                + str(te)
                            )
                        except dynamodb_client.exceptions.RequestLimitExceeded as re:
                            self.logger.error(
                                "TSensor: Update Dynamo: RequestLimitExceeded "
                                + str(re)
                            )
                        except dynamodb_client.exceptions.InternalServerError as se:
                            self.logger.error(
                                "TSensor: Update Dynamo: InternalServerError " + str(se)
                            )
                        except BaseException as e:
                            print(e)
                            self.logger.error(
                                "TSensor: Update Dynamo: Error uploading item"
                                + str(res_json)
                            )

                else:
                    poll_flag = False
                    self.logger.info("TSensor: No new runnable insights found!")
            time.sleep(2)
        return None

    def get_row_data(self, data):
        return [obj["VarCharValue"] for obj in data["Data"]]

    def update_checksum(self, insight_name):
        s3_resx = boto3.resource("s3")
        insight_name = insight_name.replace("/", "")
        try:
            s3Obj = s3_resx.Object(
                CODE_BUCKET, INSIGHT_INPUT + insight_name + "/config.json"
            )
            config_content = s3Obj.get()["Body"].read()
            config_json = json.loads(config_content.decode("utf-8"))
            csum_input_string = config_content

            if config_json["run_code"] == "PARK":
                self.logger.warning("TSensor: Insight is in PARK mode: " + insight_name)
                return True
            s3Obj = s3_resx.Object(
                CODE_BUCKET, INSIGHT_INPUT + insight_name + "/" + insight_name + ".hql"
            )
            csum_input_string += s3Obj.get()["Body"].read()

            s3Obj = s3_resx.Object(
                CODE_BUCKET, INSIGHT_INPUT + insight_name + "/" + insight_name + ".ddl"
            )
            csum_input_string += s3Obj.get()["Body"].read()
            csum_val = hashlib.md5(csum_input_string).hexdigest()
        except BaseException as e:
            self.logger.error("TSensor: update_checksum failed for " + insight_name)
            print(traceback.format_exc())
            self.logger.error(e)
            return False

        insight_query = (
            "('"
            + insight_name.replace("/", "")
            + "','"
            + config_json["version"]
            + "','"
            + csum_val
            + "')"
        )
        self.logger.info("TSensor: Insight CSum results: " + insight_query)
        self.insights_values.append(insight_query)
        return True

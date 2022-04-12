"""
Tesseract is a wrapper that checks for any
need to rerun an insight query or initiate a query execution
"""

import base64
import io
import json
import random
import string
import time
from concurrent.futures import ThreadPoolExecutor

import boto3
import requests
from boto3.dynamodb.conditions import Attr

from tesseract.wrappers.tesflow import Tesflow
from tesseract.wrappers.teslog import Teslog
from tesseract.wrappers.tsensor import TSensor
from tesseract.wrappers.wrapper_config import (
    AIRFLOW_LOCATION,
    BASE_FLOW,
    BASE_S3,
    CODE_BUCKET,
    DAG_LIST_TTL,
    INSIGHT_DYNAMO,
    INSIGHT_INPUT,
    INSIGHT_NOTIFICATION,
)


class Tesseract:
    # constructor
    insights_list = []

    def __init__(self):
        self.teslog_obj = Teslog(io.StringIO())
        self.logger = self.teslog_obj.get_logger()
        self.logger.info("Tesseract-Mod: initiated")
        self.insights_list = []

    def get_insight_execution_list(self):
        execution_list = []
        sensorObj = TSensor(self.logger)
        result = sensorObj.get_runnable_insights()
        if result is False:
            self.logger.error(
                "TesseractMod: get_insight_execution_list: System is NOT in stable state! Needs Attention!"
            )
        dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
        table = dynamodb_client.Table("tesseract")
        dynamo_results = table.scan(FilterExpression=Attr("status").contains("PENDING"))
        data = dynamo_results["Items"]
        for element in data:
            execution_list.append(element["insight"])
        print("Tesseract: Insights that has a change in signature & needs to be run---")
        print(execution_list)
        self.logger.info(
            "TesseractMod:get_insight_execution_list: New runnable insights"
            + str(execution_list)
        )
        self.logger.info(
            "TesseractMod:get_insight_execution_list: Checking for Insights to be re-generated"
        )
        regen_list = self.get_regen_insights(execution_list)
        self.logger.info(
            "TesseractMod:get_insight_execution_list: Insights requiring regeneration = "
            + str(regen_list)
        )
        if len(regen_list) > 0:
            execution_list.extend(regen_list)
            try:
                for item in regen_list:
                    table.put_item(
                        Item={
                            "insight": item,
                            "status": "PENDING,",
                        },
                        TableName=INSIGHT_DYNAMO,
                    )
            except BaseException as e:
                self.logger.error(
                    "TesseractMod: get_insight_execution_list: Failed to update Dynamo for regen list"
                )
                self.logger.error(e)
        self.logger.info(
            "TesseractMod:get_insight_execution_list: Clearing success files"
        )
        if len(execution_list) > 0:
            s3_resx = boto3.resource("s3")
            for item in execution_list:
                try:
                    file_name = INSIGHT_NOTIFICATION + item + "/_SUCCESS"
                    s3_bucket = BASE_S3.strip("s3://")
                    s3_resx.Object(s3_bucket, file_name).delete()
                except BaseException as e:
                    self.logger.error(
                        "TesseractMod: get_insight_execution_list: Failed to delete success file"
                    )
                    self.logger.error(e)
        print("Tesseract Generating code .............")
        self.logger.info(
            "TesseractMod:get_insight_execution_list: Initiating workers to Generate code for insights"
        )
        if len(execution_list) > 0:
            with ThreadPoolExecutor(max_workers=3) as executor:
                results = executor.map(self.generate_task_dag, execution_list)
                self.logger.info("Results from thread = " + str(results))
        else:
            self.logger.info(
                "TesseractMod:get_insight_execution_list: No new runnable insights"
            )

    def get_regen_insights(self, execution_list):
        regen_list = []
        s3_resx = boto3.resource("s3")
        for item in execution_list:
            try:
                s3_obj = s3_resx.Object(
                    CODE_BUCKET, INSIGHT_INPUT + item + "/config.json"
                )
                config_content = s3_obj.get()["Body"].read().decode("utf-8")
                config_json = json.loads(config_content)
                if ("depends_on" in config_json) and ("regenerate" in config_json):
                    if config_json["regenerate"].lower() == "all":
                        depends = config_json["depends_on"]
                        for depend_item in depends:
                            if depend_item not in execution_list:
                                regen_list.append(depend_item)
            except BaseException as e:
                self.logger.error(
                    "TesseractMod: get_regen_insights: Error reading config for "
                    + str(item)
                )
                self.logger.error(e)
        return regen_list

    def generate_task_dag(self, insight_name):
        s3_resx = boto3.resource("s3")
        dag_type = "tena"
        interval = "None"
        storage = "s3"
        dynamo_key = None
        depends_on = None
        email = "ankush.prasad@godaddy.com"
        rand_string = string.ascii_letters
        dag_id = (
            insight_name + "_" + "".join(random.choice(rand_string) for i in range(4))
        )
        try:
            s3_obj = s3_resx.Object(
                CODE_BUCKET, INSIGHT_INPUT + insight_name + "/config.json"
            )
            config_content = s3_obj.get()["Body"].read().decode("utf-8")
            config_json = json.loads(config_content)
            if "type" in config_json:
                if config_json["type"].lower() == "athena":
                    dag_type = "tena"
                if config_json["type"].lower() == "emr":
                    dag_type = "emr"
            if "frequency" in config_json:
                if self.validate(config_json["frequency"], "frequency"):
                    interval = config_json["frequency"]
                    if interval != "None":
                        interval = "'@" + interval + "'"
            if "email" in config_json:
                if self.validate(config_json["email"], "email"):
                    email = config_json["email"]
            if "storage" in config_json:
                if self.validate(config_json["storage"], "storage"):
                    storage = config_json["storage"]
            if "insight_key" in config_json:
                dynamo_key = config_json["insight_key"]
            if "depends_on" in config_json:
                depends_on = config_json["depends_on"]
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: generate_task_dag: config file read failed for "
                + insight_name
            )
            self.logger.error(e)
            return False
        tesflow_obj = Tesflow(
            insight_name,
            dag_id,
            dag_type,
            interval,
            storage,
            dynamo_key,
            depends_on,
            self.logger,
        )
        failure_content = (
            "Your request for generating insights: <b> "
            + insight_name
            + "</b> unfortunately <label style='color:red;'> failed </label> ."
            + " <br>Please Check your submitted query again!"
        )
        tesflow_obj.add_failure_mail(email, failure_content)
        success_content = (
            "Your request for generating insights: <b> "
            + insight_name
            + " </b> has been <label style='color:green;'> completed successfully.</label> "
            + "<br> Please click the link to query results "
        )

        tesflow_obj.add_success_mail(email, success_content)
        dag_string = tesflow_obj.get_code()
        self.logger.info("Tesseract_Mod: generate_task_dag: DAG Generated ----")
        self.logger.info(dag_string)
        self.logger.info("***********************")
        print("Deleting Existing Dag")
        self.delete_existing_dag(insight_name)
        try:
            print("Uploading Directed Acyclic graph to AWS....")
            self.logger.info(
                "Tesseract_Mod: generate_task_dag: Uploading Directed Acyclic graph to AWS"
            )
            s3_resx.Object(CODE_BUCKET, AIRFLOW_LOCATION + dag_id + "_dag.py").put(
                Body=dag_string
            )
            print("Triggering Execution...")
            self.logger.info("Tesseract_Mod: generate_task_dag: Triggering execution")
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: generate_task_dag: DAG push failed for " + insight_name
            )
            self.logger.error(e)
            return False
        try:
            self.trigger_dag(insight_name, dag_id)
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: generate_task_dag: DAG Trigger failed for "
                + insight_name
            )
            self.logger.error(e)
            return False

    """
        try:
            self.delete_dynamo_item(insight_name)
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: generate_task_dag: Dynamo update failed " + insight_name
            )
            self.logger.error(e)
"""

    def generate_task_dag_from_template(self, insight_name):
        s3_resx = boto3.resource("s3")
        s3_obj = s3_resx.Object(CODE_BUCKET, BASE_FLOW)
        dag_string = s3_obj.get()["Body"].read().decode("utf-8")
        dag_string = dag_string.replace("__INSIGHT__", insight_name)
        dag_string = dag_string.replace("__INTERVAL__", "schedule_interval=None")

        try:
            s3Obj = s3_resx.Object(
                CODE_BUCKET, INSIGHT_INPUT + insight_name + "/config.json"
            )
            config_content = s3Obj.get()["Body"].read().decode("utf-8")
            config_json = json.loads(config_content)
            if "email" in config_json:
                dag_string = dag_string.replace("__TOEMAIL__", config_json["email"])
            else:
                dag_string = dag_string.replace("__TOEMAIL__", "aprasad2@godaddy.com")
            dag_string = dag_string.replace("__CCEMAIL__", "aprasad2@godaddy.com")
        except Exception as e:
            self.logger.error(
                "Tesseract_Mod: generate_task_dag: config file read failed for "
                + insight_name
            )
            self.logger.error(e)
            return False
        print("\n=========================================================")
        print(dag_string)
        print("\n=========================================================")
        try:
            print("Uploading Directed Acyclic graph to AWS....")
            s3_resx.Object(
                CODE_BUCKET, AIRFLOW_LOCATION + insight_name + "_dag.py"
            ).put(Body=dag_string)
            print("Triggering Execution...")
            self.trigger_dag(insight_name)
        except Exception as e:
            self.logger.error(
                "Tesseract_Mod: generate_task_dag: DAG push failed for " + insight_name
            )
            self.logger.error(e)
        try:
            self.delete_dynamo_item(insight_name)
        except Exception as e:
            self.logger.error("Tesseract_Mod: Dynamo update failed " + insight_name)
            self.logger.error(e)

    def delete_dynamo_item(self, insight_name):
        self.logger.info("Tesseract_Mod: delete_dynamo_item: Function Entered")
        dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
        table = dynamodb_client.Table(INSIGHT_DYNAMO)
        dynamo_results = table.scan(FilterExpression=Attr("insight").eq(insight_name))
        data = dynamo_results["Items"]
        for element in data:
            self.logger.info(
                "Tesseract_Mod: delete_dynamo_item: "
                + insight_name
                + " status: "
                + element["status"]
            )
            response = table.delete_item(Key={"insight": insight_name})
            self.logger.info(
                "Tesseract_Mod: delete_dynamo_item: Item deletion status "
                + str(response)
            )

    def delete_existing_dag(self, insight_name):
        dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
        table = dynamodb_client.Table(INSIGHT_DYNAMO)
        base = " "
        try:
            response = table.get_item(Key={"insight": insight_name})
            self.logger.info("Item response = " + str(response))
            base = response["Item"]
            status = base["status"]
            self.logger.info("status value = " + str(status))
        except BaseException as e:
            self.logger.info(
                "Tesseract_Mod: delete_existing_dag: get_item response for "
                + str(insight_name)
                + " "
                + str(e)
            )
        deletion_candidates = []
        base_value_array = []
        if len(status) > 2:
            base_value_array = status.split(",")
            for item in base_value_array:
                if len(item) > 1 and "PENDING" not in item and "PROCESSING" not in item:
                    deletion_candidates.append(item)
        print(deletion_candidates)
        self.logger.info(
            "Tesseract_Mod: delete_existing_dag: Deletion candidates array -"
        )
        self.logger.info(deletion_candidates)
        if len(deletion_candidates) == 0:
            return
        s3_resx = boto3.resource("s3")
        for dag_value in deletion_candidates:
            # remove underlying file from s3
            try:
                dag_obj = s3_resx.Object(
                    CODE_BUCKET, AIRFLOW_LOCATION + dag_value + "_dag.py"
                )
                dag_obj.delete()
            except BaseException as e:
                self.logger.error(
                    "Tesseract_Mod: delete_existing_dag: "
                    + "Either the object is not present or is not deletable for "
                    + insight_name
                )
                self.logger.error(e)
            delete_dag = "dags delete -y tesseract_" + dag_value
            self.logger.info(
                "Tesseract_Mod: delete_existing_dag: Delete Existing DAG for "
                + insight_name
                + " is being initiated"
            )
            try:
                result = self.execute_mwaa(delete_dag, insight_name)
                self.logger.info(
                    "Tesseract_Mod: delete_existing_dag: Dag delete post call result = "
                    + str(result)
                )
            except BaseException as e:
                self.logger.info(
                    "Tesseract_Mod: delete_existing_dag: EXCEPTION with execute_mwaa = "
                    + str(e)
                )
            self.logger.info(
                "Tesseract_Mod: delete_existing_dag: Sleeping for = "
                + str(DAG_LIST_TTL)
            )
            time.sleep(DAG_LIST_TTL)
        self.delete_dynamo_item(insight_name)
        return True

    def trigger_dag(self, insight_name, dag_id):
        unpause_dag = "dags unpause tesseract_" + dag_id
        dag_flag = False
        poll_cycles = 5
        while dag_flag is False and poll_cycles > 0:
            self.logger.info(
                "Tesseract_Mod: trigger_dag: cycles remaining = " + str(poll_cycles)
            )
            dag_flag = self.execute_mwaa(unpause_dag, insight_name)
            poll_cycles = poll_cycles - 1
            time.sleep(DAG_LIST_TTL)
        if dag_flag is False:
            self.logger.error(
                "Tesseract_Mod: trigger_dag : DAG cannot be found " + str(insight_name)
            )
            return False

        trigger_dag = "dags trigger " + " tesseract_" + dag_id

        print("Triggering Dag for insight: " + str(insight_name))

        poll_cycles = 3
        result = False
        while result is False and poll_cycles > 0:
            self.logger.info(
                "Tesseract_Mod: trigger_dag: cycles remaining = " + str(poll_cycles)
            )
            result = self.execute_mwaa(trigger_dag, insight_name)
            poll_cycles = poll_cycles - 1
            if result is False:
                time.sleep(DAG_LIST_TTL)
        self.logger.info(
            "Tesseract_Mod: trigger_dag: Dag Trigger post call result = " + str(result)
        )

        if result is False:
            return
        dynamodb_client = boto3.resource("dynamodb", region_name="us-west-2")
        table = dynamodb_client.Table(INSIGHT_DYNAMO)
        base = ""
        try:
            response = table.get_item(Key={"insight": insight_name})
            base = response["Item"]["status"]
            print(base)
        except BaseException as e:
            self.logger.info(
                "TSensor: update_dynamo: get_item response for "
                + str(insight_name)
                + " "
                + str(e)
            )
        new_base = base.replace("PENDING,", "")
        statum = "PROCESSING,"
        if len(new_base) != 0:
            statum += str(new_base) + ","
        response = table.put_item(
            Item={
                "insight": insight_name,
                "status": statum + dag_id,
            },
            TableName=INSIGHT_DYNAMO,
        )
        print("Insight marked as processing = " + str(response))
        self.logger.info(
            "Tesseract_Mod: trigger_dag: Insight is marked as processsing"
            + str(response)
        )

    def validate(self, val, label):
        interval_list = ["None", "once", "hourly", "daily", "weekly"]
        storage_list = ["s3", "dynamo"]
        if label == "frequency":
            if val in interval_list:
                return True
        if label == "email":
            if val.endswith("@godaddy.com"):
                return True
        if label == "storage":
            if val in storage_list:
                return True
        return False

    def check_dagload(self, insight_name, json_arr_string):
        json_arr_object = json.loads(json_arr_string)
        print("from check_dagload")
        print(json_arr_object)
        for obj in json_arr_object:
            if obj["dag_id"] == "tesseract_" + insight_name:
                return True
        return False

    def execute_mwaa(self, dag_command, insight_name):
        airflow_client = boto3.client("mwaa")
        response = airflow_client.create_cli_token(Name="tesseract-airflow")
        auth_token = response.get("CliToken")
        hed = {"Content-Type": "text/plain", "Authorization": "Bearer " + auth_token}
        url = "https://{web_server}/aws_mwaa/cli".format(
            web_server=response.get("WebServerHostname")
        )
        resp = None
        output = None
        error_output = None
        try:
            resp = requests.post(url, data=dag_command, headers=hed)
            print(resp.__dict__)
            self.logger.info(
                "Tesseract_Mod: execute_mwaa: Dag Command execution result = "
                + str(resp)
            )
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: execute_mwaa: Exception with post request execution "
                + str(dag_command)
            )
            self.logger.error(e)
            return False
        print(resp.__dict__)
        if resp.status_code != 200:
            self.logger.error(
                "Tesseract_Mod: execute_mwaa: Bad request while running - "
                + str(dag_command)
            )
            return False
        try:
            output = base64.b64decode(resp.json()["stdout"]).decode("utf8")
            print(output)
            self.logger.info(
                "Tesseract_Mod: execute_mwaa: Command execution output = " + str(output)
            )
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: execute_mwaa: Exception while decoding output"
            )
            self.logger.error(e)
            return False
        try:
            error_output = base64.b64decode(resp.json()["stderr"]).decode("utf8")
            print(error_output)
            self.logger.info(
                "Tesseract_Mod: execute_mwaa: Command execution error output ="
                + str(error_output)
            )
        except BaseException as e:
            self.logger.error(
                "Tesseract_Mod: execute_mwaa: Exception while decoding error output"
            )
            self.logger.error(e)

        if insight_name in output:
            if "paused" in output or "triggered" in output:
                return True
        if insight_name in error_output:
            return False
        return False

    def upload_all_logs(self):
        self.teslog_obj.upload_logs()

import time

import boto3
from resolver_config import BASE_S3


def tena_get_resolver(event, context):
    table_name = deduce_table_name(event["method"])
    if table_name is None:
        return {"status": "400", "message": "source not found"}
    try:
        athena_client = boto3.client("athena")
        dummy_response = athena_client.get_table_metadata(
            CatalogName="AwsDataCatalog", DatabaseName="tesseract", TableName=table_name
        )
        print(dummy_response)
        key_value = event["key"]
        query_response = athena_client.start_query_execution(
            QueryString="SELECT * FROM "
            + table_name
            + " WHERE "
            + key_value
            + "='"
            + event["arguments"][key_value]
            + "';",
            QueryExecutionContext={"Database": "tesseract"},
            ResultConfiguration={
                "OutputLocation": BASE_S3 + "/athena_resolver/",
            },
        )

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
                poll_flag = False
                print(failure_reason)
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
                    result = [
                        dict(zip(header, [obj["VarCharValue"] for obj in row["Data"]]))
                        for row in rows
                    ]
                    return result[0]
            time.sleep(1)
    except BaseException as exp:
        return {"status": "500", "message": str(exp)}
    return {"status": "500", "message": "Athena query failed!"}


def deduce_table_name(method):
    if method.startswith("get_"):
        return method[4:]
    else:
        return None

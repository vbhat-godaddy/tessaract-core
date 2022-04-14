import sys
import boto3
import requests
import json
import base64
import time


def file_to_string(file_name):
    file_obj = open(file_name)
    content_string = file_obj.read()
    content_string = content_string.replace("__ROLE__", sys.argv[3])
    content_string = content_string.replace("__ACCESS__", sys.argv[1])
    content_string = content_string.replace("__ROLE__", sys.argv[2])
    return content_string

def initiate_connection():
    airflow_client = boto3.client("mwaa")
    response = airflow_client.create_cli_token(Name="tesseract-airflow")
    auth_token = response.get("CliToken")
    hed = {"Content-Type": "text/plain", "Authorization": "Bearer " + auth_token}
    url = "https://{web_server}/aws_mwaa/cli".format(
        web_server=response.get("WebServerHostname")
    )
    print(url)
    role_dict = {"role_arn": sys.argv[3]}
    create_connection = "connections add --conn-login " + str(sys.argv[1]) \
              + " --conn-password " + str(sys.argv[2]) \
              + " --conn-extra " + json.dumps(role_dict) \
              + " --conn-type " + "aws" + " --conn_id tesseract_aws_conn"
    print(create_connection)
    try:
        resp = requests.post(url, data="dags unpause tesseract_connection", headers=hed)
        print(resp.__dict__)
        time.sleep(60)
        resp = requests.post(url, data="dags trigger tesseract_connection", headers=hed)
        print(resp.__dict__)
        output = base64.b64decode(resp.json()["stdout"]).decode("utf8")
        print(output)
    except BaseException as e:
        print(e)

def upload_connection():
    content_string = file_to_string("scripts/tesseract_connection_base.py")
    s3_resx = boto3.resource("s3")
    s3_resx.Object(sys.argv[4], "airflow_environment/dags/tesseract_connection_base.py").put(
        Body=content_string
    )
    time.sleep(60)
    initiate_connection()
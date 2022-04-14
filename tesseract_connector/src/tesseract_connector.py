import boto3
import requests
import json
import logging
import time
import base64


def file_to_string(file_name,secretid,role):
    file_obj = open(file_name)
    content_string = file_obj.read()
    content_string = content_string.replace("__SECRET_ID__",secretid)
    content_string = content_string.replace("__ROLE__", role)
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
    '''
    try:
        session = boto3.session.Session()
        secret_client = session.client(service_name='secretsmanager')
        response = secret_client.get_secret_value(
            SecretId=deploy_secret_id
        )
        secretJSON = json.loads(response["SecretString"])

        role_dict = {"role_arn": role}
        create_connection = "connections add --conn-login " + secretJSON["AccessKeyId"] \
          + " --conn-password " + secretJSON["SecretAccessKey"] \
          + " --conn-extra " + json.dumps(role_dict) \
          + " --conn-type " + "aws" + " tesseract_aws_conn"
        print(create_connection)
        resp = requests.post(url, data=create_connection, headers=hed)
        print(resp.__dict__)
    except BaseException as e:
        print(e)
    '''
    try:
        resp = requests.post(url, data="dags unpause tesseract_connection", headers=hed)
        print(resp.__dict__)
        time.sleep(60)
        response = airflow_client.create_cli_token(Name="tesseract-airflow")
        auth_token = response.get("CliToken")
        hed = {"Content-Type": "text/plain", "Authorization": "Bearer " + auth_token}
        resp = requests.post(url, data="dags trigger tesseract_connection", headers=hed)
        print(resp.__dict__)
        output = base64.b64decode(resp.json()["stdout"]).decode("utf8")
        print(output)
    except BaseException as e:
        print(e)

def upload_connection(role,secretid):
    content_string = file_to_string("tesseract_connection_base.py",secretid,role)
    s3_resx = boto3.resource("s3")
    ssm_client = boto3.client("ssm")
    env_response = ssm_client.get_parameter(Name='/AdminParams/Team/Environment')
    env_val = env_response['Parameter']['Value']
    name_response = ssm_client.get_parameter(Name='/AdminParams/Team/Name')
    team_name_val = name_response['Parameter']['Value']
    bucket = "gd-" + team_name_val + "-" + env_val + "-tesseract"
    s3_resx.Object(bucket, "airflow_environment/dags/tesseract_connection_base.py").put(
        Body=content_string
    )
    time.sleep(60)

def connector_handler(event, context):
    upload_connection(event['role_arn'], event['deploy_secret_id'])
    initiate_connection()
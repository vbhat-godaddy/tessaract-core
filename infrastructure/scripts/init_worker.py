import boto3
import botocore
import os
import json

def create_connection():
    config = botocore.config.Config(connect_timeout=900, read_timeout=910, retries={"max_attempts": 0})
    lambda_client = boto3.client("lambda", config=config)
    env_val = os.environ['env_val']
    team_name_val = os.environ['team_name_val']
    secret_id = os.environ['secret_id']
    role = os.environ['role']
    extra_json = {"role_arn": role, "deploy_secret_id": secret_id }
    function_name = "gd-" + team_name_val + "-" + env_val + "-tesseract-connector-runner"
    response = lambda_client.invoke(
      FunctionName=function_name,
      Payload=json.dumps(extra_json),
    )
    print(response)

create_connection()
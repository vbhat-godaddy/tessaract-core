import sys
import boto3
import requests
import json

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
role_dict = {"role_arn": sys.argv[3]}
create_connection = "connections add --conn-login " + sys.argv[1] \
          + " --conn-password " + sys.argv[2] \
          + " --conn-extra " + json.dumps(role_dict) \
          + " --conn-type " + "aws"
print(create_connection)
try:
    resp = requests.post(url, data=create_connection, headers=hed)
    print(resp.__dict__)

except BaseException as e:
    print(e)
print(resp.__dict__)
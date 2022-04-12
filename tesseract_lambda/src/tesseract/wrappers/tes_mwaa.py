import base64

import boto3
import requests

mwaa_env_name = "dridata_v2"
dag_name = "tesseract_test_insight1"
mwaa_cli_command = "connections get dri_aws_conn"

client = boto3.client("mwaa")

mwaa_cli_token = client.create_cli_token(Name=mwaa_env_name)

mwaa_auth_token = "Bearer " + mwaa_cli_token["CliToken"]
mwaa_webserver_hostname = "https://{0}/aws_mwaa/cli".format(
    mwaa_cli_token["WebServerHostname"]
)
raw_data = "{0}".format(mwaa_cli_command)

mwaa_response = requests.post(
    mwaa_webserver_hostname,
    headers={"Authorization": mwaa_auth_token, "Content-Type": "text/plain"},
    data=raw_data,
    timeout=600,
)
print(mwaa_response.__dict__)

mwaa_std_err_message = base64.b64decode(mwaa_response.json()["stderr"]).decode("utf8")
mwaa_std_out_message = base64.b64decode(mwaa_response.json()["stdout"]).decode("utf8")

print(mwaa_response.status_code)
print(mwaa_std_err_message)
print(mwaa_std_out_message)

"""
CLI_JSON=$(aws mwaa --region us-west-2 create-cli-token --name dridata_v2) \
  && CLI_TOKEN=$(echo $CLI_JSON | jq -r '.CliToken') \
  && WEB_SERVER_HOSTNAME=$(echo $CLI_JSON | jq -r '.WebServerHostname') \
  && CLI_RESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli" \
  --header "Authorization: Bearer $CLI_TOKEN" \
  --header "Content-Type: text/plain" \
  --data-raw "connections get dri_aws_conn") \
  && echo "Output:" \
  && echo $CLI_RESULTS | jq -r '.stdout' | base64 --decode \
  && echo "Errors:" \
  && echo $CLI_RESULTS | jq -r '.stderr' | base64 --decode
"""

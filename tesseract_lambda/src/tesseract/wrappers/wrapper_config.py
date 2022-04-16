import boto3
from base_config import ACC_ID, TEAM_VAL, ACC_REGION, ACC_ENV
ssm_client = boto3.client("ssm")
env_response = ssm_client.get_parameter(Name='/AdminParams/Team/Environment')
env_val = env_response['Parameter']['Value']
name_response = ssm_client.get_parameter(Name='/AdminParams/Team/Name')
team_name_val = name_response['Parameter']['Value']
bucket = "gd-" + TEAM_VAL + "-" + ACC_ENV + "-tesseract"
account_id = boto3.client('sts').get_caller_identity().get('Account')
BASE_S3 = "s3://" + bucket
CODE_BUCKET = bucket
ATHENA_RESULTS = "tena_results"
INSIGHT_INPUT = "tesseract_input/"
INSIGHT_NOTIFICATION = "tesseract_notification/"
CALLBACK_TOPIC = "arn:aws:sns:" + ACC_REGION + ":" + ACC_ID + ":tesseract-notify"
CURRENT_CSUM = "insight_csum_cur"
VAULT_CSUM = "insight_csum_vault"
INSIGHT_TABLE = "runnable_insights"
INSIGHT_DYNAMO = "tesseract"
TESSERACT_LOG = "tesseract_logs/"
DAG_LIST_TTL = 70
BASE_FLOW = "code/wrapper_base_dag.py"
AIRFLOW_LOCATION = "airflow_environment/dags/"
SYNC_SOURCE_ROLEARN = (
    "arn:aws:iam::" + ACC_ID + ":role/" + TEAM_VAL + "-custom-tesseract-auth-cognito"
)
SYNC_API_ID = "qk6gr5oyy5fpxgacwzann4orom"
SYNC_LAMBDA_RESOLVEARN = (
    "arn:aws:lambda:" + ACC_REGION + ":" + ACC_ID + ":function:"
    + "gd-" + TEAM_VAL + "-" + ACC_ENV + "-tes-athena-get-resolver-runner"
)

import boto3
from base_config import ACC_ID, TEAM_VAL, ACC_REGION, ACC_ENV
client = boto3.client('appsync')
response = client.list_graphql_apis()
api_arr = response['graphqlApis']
api_id = None
for api_resp in api_arr:
    if api_resp['name'] == "tesseract-sync":
        api_id = api_resp['apiId']
bucket = "gd-" + TEAM_VAL + "-" + ACC_ENV + "-tesseract"
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
TES_DYN_WORKER_CNT=1
SYNC_SOURCE_ROLEARN = (
    "arn:aws:iam::" + ACC_ID + ":role/" + TEAM_VAL + "-custom-tes-lambda-role"
)
SYNC_API_ID = api_id
SYNC_LAMBDA_RESOLVEARN = (
    "arn:aws:lambda:" + ACC_REGION + ":" + ACC_ID + ":function:"
    + "gd-" + TEAM_VAL + "-" + ACC_ENV + "-tes-athena-get-resolver-runner"
)

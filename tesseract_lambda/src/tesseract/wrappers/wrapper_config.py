BASE_S3 = "s3://gd-findml-dev-private-tesseract"
CODE_BUCKET = "gd-findml-dev-private-tesseract"
ATHENA_RESULTS = "tena_results"
INSIGHT_INPUT = "tesseract_input/"
INSIGHT_NOTIFICATION = "tesseract_notification/"
CALLBACK_TOPIC = "arn:aws:sns:us-west-2:131859756021:tesseract-notify"
CURRENT_CSUM = "insight_csum_cur"
VAULT_CSUM = "insight_csum_vault"
INSIGHT_TABLE = "runnable_insights"
INSIGHT_DYNAMO = "tesseract"
TESSERACT_LOG = "tesseract_logs/"
DAG_LIST_TTL = 70
BASE_FLOW = "code/wrapper_base_dag.py"
AIRFLOW_LOCATION = "airflow_environment/dags/"
SYNC_SOURCE_ROLEARN = (
    "arn:aws:iam::131859756021:role/findml-custom-tesseract-auth-cognito"
)
SYNC_API_ID = "qk6gr5oyy5fpxgacwzann4orom"
SYNC_LAMBDA_RESOLVEARN = (
    "arn:aws:lambda:us-west-2:131859756021:function:"
    + "gd-findml-dev-private-tes-athena-get-resolver-runner"
)

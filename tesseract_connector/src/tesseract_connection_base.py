import json
from datetime import timedelta

from airflow import models, settings
from airflow.models import Connection
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.utils import dates
import boto3

dag_id = "tesseract_connection"
args = {"owner": "tesseract", "retries": 1, "retry_delay": timedelta(minutes=2)}
with models.DAG(
    dag_id=dag_id,
    schedule_interval=None,
    start_date=dates.days_ago(1),  # Change to suit your needs
    max_active_runs=1,
    catchup=False,
    default_args=args,
    tags=["tesseract"],
) as dag:
    dag.doc_md = "Tesseract Secrets Refresher"

    def create_connection(**kwargs):
        role = kwargs["role"]
        session = boto3.session.Session()
        secret_client = session.client(service_name='secretsmanager')
        response = secret_client.get_secret_value(
            SecretId="__SECRET_ID__"
        )
        secretJSON = json.loads(response["SecretString"])
        session = settings.Session()
        # delete existing connection
        connobj = Connection(
            conn_id="tesseract_aws_conn",
            login=secretJSON["AccessKeyId"],
            password=secretJSON["SecretAccessKey"],
            conn_type="aws",
            extra='{"role_arn":"' + role + '"}',
        )
        # add connection to the session and commit
        session.add(connobj)
        session.commit()

    create_connection_step = PythonOperator(
        task_id="create_conn",
        python_callable=create_connection,
        op_kwargs={
            "role": "__ROLE__"
        },
        trigger_rule="one_success",
        dag=dag,
    )

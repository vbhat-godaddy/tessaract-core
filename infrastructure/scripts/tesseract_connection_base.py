import json
from datetime import timedelta

from airflow import models, settings
from airflow.models import Connection
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.utils import dates

dag_id = "tesseract_connection"
args = {"owner": "tesseract", "retries": 1, "retry_delay": timedelta(minutes=2)}
with models.DAG(
    dag_id=dag_id,
    schedule_interval=None,
    start_date=dates.days_ago(1),  # Change to suit your needs
    max_active_runs=1,
    catchUp=False,
    default_args=args,
    tags=["tesseract"],
) as dag:
    dag.doc_md = "Tesseract Secrets Refresher"

    def create_connection(**kwargs):
        access = kwargs["access"]
        secret = kwargs["secret"]
        role = kwargs["role"]
        session = settings.Session()
        # delete existing connection
        connobj = Connection(
            conn_id="tesseract_aws_conn",
            login=access,
            password=secret,
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
            "access": "__ACCESS__",
            "secret": "__SECRET__",
            "role": "__ROLE__"
        },
        trigger_rule="one_success",
        dag=dag,
    )

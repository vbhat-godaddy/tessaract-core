import json
from datetime import timedelta

from airflow import models, settings
from airflow.models import Connection
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.utils import dates

dag_id = "tesseract_refresh_creds"
args = {"owner": "tesseract", "retries": 1, "retry_delay": timedelta(minutes=2)}
with models.DAG(
    dag_id=dag_id,
    schedule_interval=timedelta(days=1),
    start_date=dates.days_ago(1),  # Change to suit your needs
    max_active_runs=1,
    default_args=args,
    tags=["tesseract"],
) as dag:
    dag.doc_md = "Tesseract Secrets Refresher"

    def refresh_secrets(**kwargs):
        deploy_role = kwargs["role"]
        conn = "tesseract_aws_conn"
        client = AwsBaseHook(
            aws_conn_id=conn, client_type="secretsmanager"
        ).get_client_type("secretsmanager")
        # get secret value for provided Secret ID
        response = client.get_secret_value(
            SecretId="__SECRET_ID__"
        )
        # Convert string version of Secret params to JSON
        secretJSON = json.loads(response["SecretString"])
        # Obtain the session to modify Airflow DB
        session = settings.Session()
        # delete existing connection
        prev_conn_obj = (
            session.query(Connection).filter(Connection.conn_id == conn).first()
        )
        if prev_conn_obj is not None:
            session.delete(prev_conn_obj)
            session.commit()
        # create a new connection with new parameters
        connobj = Connection(
            conn_id=conn,
            login=secretJSON["AccessKeyId"],
            password=secretJSON["SecretAccessKey"],
            conn_type="aws",
            extra='{"role_arn":"' + deploy_role + '"}',
        )
        # add connection to the session and commit
        session.add(connobj)
        session.commit()

    refresh_secrets_step = PythonOperator(
        task_id="refresh_secrets",
        python_callable=refresh_secrets,
        op_kwargs={
            "role": "__ROLE__"
        },
        trigger_rule="one_success",
        dag=dag,
    )

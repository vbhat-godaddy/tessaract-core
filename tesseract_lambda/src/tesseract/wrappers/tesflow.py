"""
Tesseract-Airflow (Tesflaw) is a wrapper that generated an Airflow
DAG based on submitted requests, self identifies the infrastructure
"""
from tesseract.wrappers.wrapper_config import BASE_S3, INSIGHT_NOTIFICATION


class Tesflow:
    code_block = None
    task_dict = {
        "tena": ["purge_schema", "create_schema", "create_insight", "generate_link"],
        "emr": ["purge_schema", "create_schema", "create_emr_insight"],
        "dynamo": [
            "delete_dynamo",
            "create_dynamo",
            "create_dynamo_data",
            "copy_dynamo",
            "mark_processed_dynamo",
            "update_gql",
        ],
    }
    dag_type = None
    insight_name = None
    storage = None
    dynamo_key = None

    # constructor
    def __init__(
        self,
        insight_name,
        dag_id,
        dag_type,
        interval,
        storage,
        dynamo_key,
        depends_on,
        logger,
    ):
        print("Constructor")
        self.logger = logger
        self.logger.info("TesFlow: Constructor: Initiated")
        self.code_block = []
        self.dag_type = dag_type
        self.insight_name = insight_name
        self.dag_id = dag_id
        self.storage = storage
        self.dynamo_key = dynamo_key
        self.depends_on = depends_on
        self.init_headers()
        self.add_model(interval)
        self.add_tasks()

    def init_headers(self):
        header_block = """from airflow import models
from airflow.exceptions import AirflowException
from airflow.operators import dummy_operator, email_operator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils import dates
from airflow.sensors.s3_key_sensor import S3KeySensor
from datetime import datetime, timedelta
"""
        if self.dag_type == "emr":
            header_block += """from libs.emr_launch_library import (
    CreateEMROperator,
    CreateEMRSensor,
    TerminateEMROperator,
)
from libs.emr_submit_and_monitor_step import EmrSubmitAndMonitorStepOperator
from tesseract.wrappers.wrapper_config import BASE_S3, INSIGHT_INPUT
"""
        self.code_block.append(header_block)
        dependency_block = "from helpers import DOCS "
        if self.dag_type == "tena":
            for item in self.task_dict["tena"]:
                dependency_block += ", {0}_op".format(item)
        if self.dag_type == "emr":
            for item in self.task_dict["emr"]:
                dependency_block += ", {0}_op".format(item)
            dependency_block += " ,generate_link_op"
        if self.storage == "dynamo":
            for item in self.task_dict["dynamo"]:
                dependency_block += ", {0}_op".format(item)
        else:
            dependency_block += ", update_gql_op"
        dependency_block += ", notify_success_op, clear_history_op"
        self.code_block.append(dependency_block)

    def add_model(self, interval):
        insight_header = "insight_name = '" + self.insight_name + "'"
        self.code_block.append(insight_header)
        insight_args = "args = {'owner': 'tesseract', 'retries': 1, 'retry_delay': timedelta(minutes=2)}"
        self.code_block.append(insight_args)
        self.code_block.append("dag_id = 'tesseract_" + self.dag_id + "'")
        if self.dag_type == "emr":
            config_block = """EMR_CONFIG = {
    'emr_release_label': 'emr-5.33.0',
    'master_instance_type': 'm5.24xlarge',
    'core_instance_type': 'r5d.8xlarge',
    'num_core_nodes': '4',
    'emr_step_concurrency': '1',
    'emr_custom_job_flow_role_name_suffix': 'emr-ec2-default-role',
    'emr_sc_bootstrap_file_path': '{0}/emrinit.sh',
}
""".format(BASE_S3)
            self.code_block.append(config_block)
        model_block = """with models.DAG(
    dag_id=dag_id,
    schedule_interval={0},
    start_date=dates.days_ago(1),  # Change to suit your needs
    max_active_runs=1,
    default_args=args,
    catchup=False,
    tags=['tesseract'],
) as dag:
    dag.doc_md = DOCS""".format(
            interval
        )
        self.code_block.append(model_block)

    def add_tasks(self):
        if self.dag_type == "tena":
            sensor_task = self.add_sensors()
            self.add_subtask(sensor_task)
            if self.storage == "dynamo":
                self.add_storagetasks(self.task_dict["tena"][-1])
            if self.storage == "dynamo":
                self.add_success_handlers(self.task_dict[self.storage][-1])
            else:
                self.add_tessync_tasks(self.task_dict[self.dag_type][-1])
                self.add_success_handlers("update_gql")
            self.add_failsafe_handlers()
        elif self.dag_type == "emr":
            self.add_emrbase_tasks()
            self.add_subtask("chk_create_emr_cluster")
            self.add_create_insight_emr()
            if self.storage == "dynamo":
                self.add_storagetasks("create_insight_step")
            if self.storage == "dynamo":
                self.add_success_handlers(self.task_dict[self.storage][-1])
            else:
                self.add_tessync_tasks("create_insight_step")
                self.add_success_handlers("update_gql")
            self.add_failsafe_handlers()
            self.add_termination_handler()

    def add_sensors(self):
        item = "clear_history"
        task_code_block = """
    {0}_ok = PythonOperator(
        task_id='{0}',
        python_callable= {0}_op,
        op_kwargs={{'insight':'{1}'}},
        trigger_rule='one_success',
        dag=dag
    )
    """.format(
            item, self.insight_name
        )
        self.code_block.append(task_code_block)
        if self.depends_on is None:
            return item
        task_code_block = (
            "    sensor_success_ok = dummy_operator.DummyOperator(task_id='sensor_success', "
            "trigger_rule='all_success')"
        )
        self.code_block.append(task_code_block)
        task_code_block = """
    sensor_success_ok.set_upstream(clear_history_ok)
    delay_sensor = BashOperator(
        task_id='delay_sensor',
        bash_command='sleep 5m',
        dag=dag)
    """
        self.code_block.append(task_code_block)
        for item in self.depends_on:
            task_code_block = """
    {0}_sensor = S3KeySensor(
        task_id='{0}_sensor',
        poke_interval=60*15,
        timeout=60 * 60 * 24,  # timeout in 24 hours
        bucket_key="{1}"
                   + "/"
                   + "{2}"
                   + "{0}"
                   + "/_SUCCESS",
        wildcard_match=False,
        dag=dag,
    )
    {0}_sensor.set_downstream(sensor_success_ok)
    {0}_sensor.set_upstream(delay_sensor)
    """.format(
                item, BASE_S3, INSIGHT_NOTIFICATION
            )
            self.code_block.append(task_code_block)
        return "sensor_success"

    def add_subtask(self, start_task):
        task_list = self.task_dict[self.dag_type]
        self.logger.info(
            "Tesflow: add_subtask: Task list being worked on: " + str(task_list)
        )
        for item in task_list:
            task_code_block = """
    {0} = PythonOperator(
        task_id='{0}',
        python_callable= {0}_op,
        op_kwargs={{'insight':'{1}'}},
        trigger_rule='one_success',
        dag=dag
    )
    """.format(
                item, self.insight_name
            )
            self.code_block.append(task_code_block)
            task_code_block = """    {0}_ok = dummy_operator.DummyOperator(
        task_id='{0}_ok',
        trigger_rule='one_success'
    )
    {0}_error = dummy_operator.DummyOperator(
        task_id='{0}_error',
        trigger_rule='one_failed'
    )
    {0}_ok.set_upstream({0})
    {0}_error.set_upstream({0})""".format(
                item
            )
            self.code_block.append(task_code_block)
            if start_task is not None:
                dependency_block = "    {0}_ok.set_downstream({1})".format(
                    start_task, item
                )
                self.code_block.append(dependency_block)
            start_task = item

    def add_tessync_tasks(self, base_op):
        task_list = self.task_dict[self.dag_type]
        self.logger.info("Tesflow: add_tessync_tasks: Tessync task being added ")
        item = "update_gql"
        task_code_block = """
    {0} = PythonOperator(
        task_id='{0}',
        python_callable= {0}_op,
        op_kwargs={{'insight':'{1}','insight_key':'{2}', 'storage':'{3}' }},
        trigger_rule='one_success',
        dag=dag
    )
    """.format(
            item, self.insight_name, self.dynamo_key, self.storage
        )
        self.code_block.append(task_code_block)
        task_code_block = """    {0}_ok = dummy_operator.DummyOperator(
                task_id='{0}_ok',
                trigger_rule='one_success'
            )
    {0}_error = dummy_operator.DummyOperator(
        task_id='{0}_error',
        trigger_rule='one_failed'
    )
    {0}_ok.set_upstream({0})
    {0}_error.set_upstream({0})""".format(
            item
        )
        self.code_block.append(task_code_block)
        if base_op is None:
            base_op = task_list[-1]
        success_block = "    {0}_ok.set_downstream(update_gql)".format(base_op)
        self.code_block.append(success_block)

    def add_storagetasks(self, start_task):
        task_list = self.task_dict[self.storage]
        self.logger.info(
            "Tesflow: add_subtask: Storage Task list being worked on: " + str(task_list)
        )
        for item in task_list:
            task_code_block = """
    {0} = PythonOperator(
        task_id='{0}',
        python_callable= {0}_op,
        op_kwargs={{'insight':'{1}','dynamo_key':'{2}', 'insight_key':'{2}', 'storage': '{3}' }},
        trigger_rule='one_success',
        dag=dag
    )
    """.format(
                item, self.insight_name, self.dynamo_key, self.storage
            )
            self.code_block.append(task_code_block)
            task_code_block = """    {0}_ok = dummy_operator.DummyOperator(
        task_id='{0}_ok',
        trigger_rule='one_success'
    )
    {0}_error = dummy_operator.DummyOperator(
        task_id='{0}_error',
        trigger_rule='one_failed'
    )
    {0}_ok.set_upstream({0})
    {0}_error.set_upstream({0})""".format(
                item
            )
            self.code_block.append(task_code_block)
            if start_task is not None:
                dependency_block = "    {0}_ok.set_downstream({1})".format(
                    start_task, item
                )
                self.code_block.append(dependency_block)
            start_task = item

    def add_emrbase_tasks(self):
        sensor_task = self.add_sensors()
        base_task_block = """
    create_emr_cluster = CreateEMROperator(
        task_id='create_emr_cluster',
        conn_id='tesseract_aws_conn',
        emr_cluster_name='mwaa_' + dag_id + '_' + '{{ ts_nodash }}',
        master_instance_type=EMR_CONFIG['master_instance_type'],
        core_instance_type=EMR_CONFIG['core_instance_type'],
        num_core_nodes=EMR_CONFIG['num_core_nodes'],
        emr_release_label=EMR_CONFIG['emr_release_label'],
        emr_sc_bootstrap_file_path=EMR_CONFIG['emr_sc_bootstrap_file_path'],
        emr_step_concurrency='1',
        emr_custom_job_flow_role_name_suffix=EMR_CONFIG[
            'emr_custom_job_flow_role_name_suffix'
        ],
    )

    create_emr_cluster_error = dummy_operator.DummyOperator(
        task_id='create_emr_cluster_error', trigger_rule='one_failed'
    )
    create_emr_cluster_ok = dummy_operator.DummyOperator(
        task_id='create_emr_cluster_ok', trigger_rule='one_success'
    )

    create_emr_cluster.set_downstream(create_emr_cluster_error)
    create_emr_cluster.set_downstream(create_emr_cluster_ok)

    chk_create_emr_cluster = CreateEMRSensor(
        task_id='chk_create_emr_cluster',
        conn_id='tesseract_aws_conn',
        provisioned_record_id=\"{{ task_instance.xcom_pull(task_ids='create_emr_cluster',\"
        \" key='return_value')[0] }}\",
        dag=dag,
    )

    chk_create_emr_cluster_error = dummy_operator.DummyOperator(
        task_id='chk_create_emr_cluster_error', trigger_rule='one_failed'
    )
    chk_create_emr_cluster_ok = dummy_operator.DummyOperator(
        task_id='chk_create_emr_cluster_ok', trigger_rule='one_success'
    )

    chk_create_emr_cluster.set_downstream(chk_create_emr_cluster_error)
    chk_create_emr_cluster.set_downstream(chk_create_emr_cluster_ok)
    create_emr_cluster_ok.set_downstream(chk_create_emr_cluster)
"""
        self.code_block.append(base_task_block)
        if sensor_task is not None:
            task_block = "    create_emr_cluster.set_upstream({0}_ok)".format(
                sensor_task
            )
            self.code_block.append(task_block)

    def add_create_insight_emr(self):
        insight_block = """
    create_insight_step = EmrSubmitAndMonitorStepOperator(
        task_id='create_insight_step',
        trigger_rule='one_success',
        steps=[
            {
                'Name': 'create_insight_step',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'hive-script',
                        '--run-hive-script',
                        '--args',
                        '-f',
                        BASE_S3 + '/' + INSIGHT_INPUT + insight_name + '/' + insight_name + '_emr.hql',
                        '-hiveconf',
                        'tez.am.resource.memory.mb=10240'
                    ],
                },
            }
        ],
        job_flow_id=\"{{ task_instance.xcom_pull(task_ids='chk_create_emr_cluster', key='job_flow_id') }}\",
        aws_conn_id='tesseract_aws_conn',
        check_interval=60,
    )
    create_insight_step_ok = dummy_operator.DummyOperator(
        task_id='sample_hive_ok', trigger_rule='one_success'
    )
    create_insight_step_error = dummy_operator.DummyOperator(
        task_id='sample_hive_error', trigger_rule='one_failed'
    )

    create_insight_step.set_downstream(create_insight_step_ok)
    create_insight_step.set_downstream(create_insight_step_error)
"""
        self.code_block.append(insight_block)
        task_list = self.task_dict[self.dag_type]
        dependency_block = "    {0}_ok.set_downstream(create_insight_step)".format(
            task_list[-1]
        )
        self.code_block.append(dependency_block)

        task_code_block = """
    {0} = PythonOperator(
       task_id='{0}',
       python_callable= {0}_op,
       op_kwargs={{'insight':'{1}'}},
       trigger_rule='one_success',
       dag=dag
    )
   """.format(
            "generate_link", self.insight_name
        )
        self.code_block.append(task_code_block)
        task_code_block = """    {0}_ok = dummy_operator.DummyOperator(
       task_id='{0}_ok',
       trigger_rule='one_success'
    )
    {0}_error = dummy_operator.DummyOperator(
       task_id='{0}_error',
       trigger_rule='one_failed'
    )
    {0}_ok.set_upstream({0})
    {0}_error.set_upstream({0})""".format(
            "generate_link"
        )
        self.code_block.append(task_code_block)
        dependency_block = "    create_insight_step_ok.set_downstream(generate_link)"
        self.code_block.append(dependency_block)

    def add_termination_handler(self):
        termination_steps = """
    terminate_emr_cluster_failure = TerminateEMROperator(
        task_id='terminate_emr_cluster_failure',
        conn_id='tesseract_aws_conn',
        provisioned_product_id=\"{{ task_instance.xcom_pull(task_ids='create_emr_cluster',\"
        \" key='return_value')[1] }}\",
        dag=dag,
        trigger_rule='one_success',
    )

    terminate_emr_cluster_success = TerminateEMROperator(
        task_id='terminate_emr_cluster_success',
        conn_id='tesseract_aws_conn',
        provisioned_product_id=\"{{ task_instance.xcom_pull(task_ids='create_emr_cluster',\"
        \" key='return_value')[1] }}\",
        dag=dag,
        trigger_rule='one_success',
    )
"""
        self.code_block.append(termination_steps)
        dependency_block = """    failure_op.set_downstream(terminate_emr_cluster_failure)
    success_op.set_downstream(terminate_emr_cluster_success)
"""
        self.code_block.append(dependency_block)

    def add_failsafe_handlers(self):
        task_list = self.task_dict[self.dag_type]
        fail_op = (
            "    failure_op = dummy_operator.DummyOperator(task_id='failure_op',"
            " trigger_rule='one_success')"
        )
        self.code_block.append(fail_op)
        for item in task_list:
            fail_block = "    {0}_error.set_downstream(failure_op)".format(item)
            self.code_block.append(fail_block)
        if self.dag_type == "emr":
            insight_block = "    create_insight_step_error.set_downstream(failure_op)"
            self.code_block.append(insight_block)
        if self.storage == "dynamo":
            for item in self.task_dict[self.storage]:
                fail_block = "    {0}_error.set_downstream(failure_op)".format(item)
                self.code_block.append(fail_block)
        else:
            fail_block = "    update_gql_error.set_downstream(failure_op)"
            self.code_block.append(fail_block)
        fail_block = "    notify_success_error.set_downstream(failure_op)"
        self.code_block.append(fail_block)

    def add_success_handlers(self, base_op):
        task_list = self.task_dict[self.dag_type]
        success_op = (
            "    success_op = dummy_operator.DummyOperator(task_id='success_op', "
            "trigger_rule='all_success')"
        )
        self.code_block.append(success_op)
        if base_op is None:
            base_op = task_list[-1]
        success_block = "    {0}_ok.set_downstream(success_op)".format(base_op)
        self.code_block.append(success_block)
        item = "notify_success"
        task_code_block = """
    {0} = PythonOperator(
        task_id='{0}',
        python_callable= {0}_op,
        op_kwargs={{'insight':'{1}'}},
        trigger_rule='one_success',
        dag=dag
    )
    """.format(
            item, self.insight_name
        )
        self.code_block.append(task_code_block)
        task_code_block = """    {0}_ok = dummy_operator.DummyOperator(
        task_id='{0}_ok',
        trigger_rule='one_success'
    )
    {0}_error = dummy_operator.DummyOperator(
        task_id='{0}_error',
        trigger_rule='one_failed'
    )
    {0}_ok.set_upstream({0})
    {0}_error.set_upstream({0})
    {0}.set_upstream(success_op)""".format(
            item
        )
        self.code_block.append(task_code_block)

    def add_failure_mail(self, to_email, content):
        task_block = """
    send_failure_email = email_operator.EmailOperator(
        task_id='send_failure_email',
        trigger_rule='one_success',
        to='{0}',
        cc='aprasad2@godaddy.com',
        bcc=None,
        subject='Tesseract needs your attention',
        html_content=\"{1}\",
    )""".format(
            to_email, content
        )
        self.code_block.append(task_block)
        dependency_block = "    failure_op.set_downstream(send_failure_email)"
        self.code_block.append(dependency_block)
        if self.dag_type == "emr":
            dependency_block2 = """    create_emr_cluster_error.set_downstream(send_failure_email)
    chk_create_emr_cluster_error.set_downstream(send_failure_email)
"""
            self.code_block.append(dependency_block2)

    def add_success_mail(self, to_email, content):
        link = "{{ task_instance.xcom_pull(task_ids='generate_link') }}"
        task_block = """
    send_success_email = email_operator.EmailOperator(
        task_id='send_success_email',
        trigger_rule='one_success',
        to='{0}',
        cc='aprasad2@godaddy.com',
        bcc=None,
        subject='Tesseract has some good news',
        html_content=\"{1} <a href='{2}'> HERE</a>\",
    )""".format(
            to_email, content, link
        )
        self.code_block.append(task_block)
        dependency_block = "    success_op.set_downstream(send_success_email)"
        self.code_block.append(dependency_block)

    def get_code(self):
        executable_string = "\n".join(self.code_block)
        return executable_string


"""
tesflow_obj = Tesflow("test_insight2", "emr", "'@daily'")
failure_content = (
    "Your request for generating insights: <b> "
    + "tes_insight2"
    + "</b> unfortunately <label style='color:red;'> failed </label> ."
    + " <br>Please Check your submitted query again!"
)
tesflow_obj.add_failure_mail("ap@gd.com", failure_content)
success_content = (
    "Your request for generating insights: <b> "
    + "tes_insight2"
    + " </b> has been <label style='color:green;'> completed successfully.</label> "
    + "<br> Please click the following link to query results"
)

tesflow_obj.add_success_mail("ap@gd.com", success_content)
dag_string = tesflow_obj.get_code()
print(dag_string)
"""

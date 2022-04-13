import time

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.providers.amazon.aws.hooks.emr import EmrHook
from airflow.sensors.base import BaseSensorOperator
from airflow.utils.decorators import apply_defaults
from botocore.exceptions import ClientError

# Class to create an EMR artifact


class CreateEMROperator(BaseOperator):

    template_fields = [
        "emr_cluster_name",
        "aws_environment",
        "emr_release_label",
        "emr_sc_bootstrap_file_path",
        "input_cluster_id",
        "master_instance_type",
        "core_instance_type",
        "num_core_nodes",
        "subnet_ids",
    ]
    template_ext = (".json",)

    @apply_defaults
    def __init__(
        self,
        *,
        conn_id="aws_default",
        aws_environment="dev-private",
        emr_cluster_name="tesseract",
        master_instance_type="m5.8xlarge",
        core_instance_type="r5d.8xlarge",
        num_core_nodes="2",
        emr_release_label="emr-5.33.0",
        emr_sc_bootstrap_file_path="s3://test-bucket/init",
        emr_sc_provisioning_artifact_name="1.8.0",
        emr_custom_job_flow_role_name_suffix="emr-ec2-default-role",
        emr_custom_service_role_name_suffix="emr-default-role",
        emr_step_concurrency="1",
        subnet_ids="/AdminParams/VPC/DXAPPSubnets",
        emr_sc_tags=[
            {"Key": "doNotShutDown", "Value": "true"},
        ],
        input_cluster_id=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.conn_id = conn_id
        self.aws_environment = aws_environment
        self.emr_cluster_name = emr_cluster_name
        self.master_instance_type = master_instance_type
        self.core_instance_type = core_instance_type
        self.num_core_nodes = str(num_core_nodes)
        self.emr_release_label = emr_release_label
        self.emr_sc_bootstrap_file_path = emr_sc_bootstrap_file_path
        self.emr_sc_provisioning_artifact_name = emr_sc_provisioning_artifact_name
        self.emr_custom_job_flow_role_name_suffix = emr_custom_job_flow_role_name_suffix
        self.emr_custom_service_role_name_suffix = emr_custom_service_role_name_suffix
        # Internally set on invocation
        self.emr_sc_product_id = None
        self.emr_sc_provisioning_artifact_id = None
        self.emr_sc_launch_path_id = None
        self.emr_sc_tags = emr_sc_tags
        self.master_security_group_id = None
        self.slave_security_group_id = None
        self.subnet_ids = subnet_ids
        self.emr_step_concurrency = emr_step_concurrency
        self.input_cluster_id = input_cluster_id

    def set_emr_service_product_ids(self):
        sc = AwsBaseHook(
            aws_conn_id=self.conn_id, client_type="servicecatalog"
        ).get_client_type("servicecatalog")
        response = sc.describe_product(Name="EMR")

        self.emr_sc_product_id = response["ProductViewSummary"]["ProductId"]
        self.emr_sc_launch_path_id = response["LaunchPaths"][0]["Id"]
        self.emr_sc_provisioning_artifact_id = next(
            (
                item
                for item in response["ProvisioningArtifacts"]
                if item["Name"] == self.emr_sc_provisioning_artifact_name
            ),
            None,
        )["Id"]

    def set_security_groups_subnet(self):
        ec2 = AwsBaseHook(aws_conn_id=self.conn_id, client_type="ec2").get_client_type(
            "ec2"
        )
        ec2_response = ec2.describe_security_groups(
            Filters=[
                {
                    "Name": "group-name",
                    "Values": [
                        "ElasticMapReduce-Slave-Private",
                        "ElasticMapReduce-Master-Private",
                    ],
                }
            ]
        )
        if not ec2_response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            raise AirflowException("Unable to get service groups: %s" % ec2_response)

        slave_security_group = next(
            (
                sg
                for sg in ec2_response["SecurityGroups"]
                if sg["GroupName"] == "ElasticMapReduce-Slave-Private"
            ),
            None,
        )

        if not slave_security_group:
            raise AirflowException("Unable to find slave security group ids")

        self.slave_security_group_id = slave_security_group["GroupId"]

        master_security_group = next(
            (
                sg
                for sg in ec2_response["SecurityGroups"]
                if sg["GroupName"] == "ElasticMapReduce-Master-Private"
            ),
            None,
        )

        if not master_security_group:
            raise AirflowException("Unable to find master security group")

        self.master_security_group_id = master_security_group["GroupId"]

    def execute(self, context):
        if self.input_cluster_id and self.input_cluster_id != "None":
            return "dummy", "dummy"  # no need to create emr cluster
        self.set_emr_service_product_ids()
        self.set_security_groups_subnet()

        sc = AwsBaseHook(
            aws_conn_id=self.conn_id, client_type="servicecatalog"
        ).get_client_type("servicecatalog")
        self.log.info(
            "Provisioning EMR cluster in subnet id: %s in %s environment",
            self.subnet_ids,
            self.aws_environment,
        )

        response = sc.provision_product(
            ProductId=self.emr_sc_product_id,
            ProvisioningArtifactId=self.emr_sc_provisioning_artifact_id,
            PathId=self.emr_sc_launch_path_id,
            ProvisionedProductName="sc-" + self.emr_cluster_name,
            Tags=self.emr_sc_tags,
            ProvisioningParameters=[
                {"Key": "ClusterName", "Value": self.emr_cluster_name},
                {"Key": "MasterInstanceType", "Value": self.master_instance_type},
                {"Key": "CoreInstanceType", "Value": self.core_instance_type},
                {"Key": "NumberOfCoreInstances", "Value": self.num_core_nodes},
                {"Key": "EbsRootVolumeSize", "Value": "10"},
                {"Key": "SubnetIDs", "Value": self.subnet_ids},
                {
                    "Key": "MasterSecurityGroupIds",
                    "Value": self.master_security_group_id,
                },
                {"Key": "SlaveSecurityGroupIds", "Value": self.slave_security_group_id},
                {"Key": "ReleaseLabel", "Value": self.emr_release_label},
                {
                    "Key": "CustomJobFlowRoleNameSuffix",
                    "Value": self.emr_custom_job_flow_role_name_suffix,
                },
                {
                    "Key": "CustomServiceRoleNameSuffix",
                    "Value": self.emr_custom_service_role_name_suffix,
                },
                {
                    "Key": "CustomApplicationListJSON",
                    "Value": """
                    [
                        {"Name": "hadoop"},
                        {"Name": "hive"},
                        {"Name": "pig"},
                        {"Name": "HCatalog"},
                        {"Name": "Spark"},
                        {"Name": "Sqoop"},
                        {"Name": "Ganglia"}
                    ]
                """,
                },
                {
                    "Key": "CustomConfigurationsJSON",
                    "Value": """
                    [
                        {
                            "Classification":"hive-site",
                            "ConfigurationProperties":{
                                "hive.metastore.schema.verification":"false",
                                "hive.metastore.client.factory.class":"com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
                                "aws.glue.catalog.separator":"/",
                                "hive.exec.stagingdir":"/tmp/hive/",
                                "hive.exec.scratchdir":"/tmp/hive/"
                            }
                        },
                        {
                            "Classification":"spark-hive-site",
                            "ConfigurationProperties":{
                                "hive.metastore.client.factory.class":"com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
                                "aws.glue.catalog.separator":"/"
                            }
                        },
                        {
                            "Classification":"mapred-site",
                            "ConfigurationProperties":{
                            "mapred.output.direct.EmrFileSystem":"false",
                            "mapred.output.direct.NativeS3FileSystem":"false"
                            }
                        },
                        {
                            "Classification": "hadoop-env",
                            "Configurations": [
                                {
                                    "Classification": "export",
                                    "ConfigurationProperties": {
                                        "HADOOP_NAMENODE_HEAPSIZE": "4096"
                                    }
                                }
                            ]
                        },
                        {
                            "Classification": "core-site",
                            "ConfigurationProperties": {
                                "fs.s3.canned.acl": "BucketOwnerFullControl",
                                "fs.s3a.acl.default": "bucket-owner-full-control"
                            }
                        }
                    ]
                """,
                },
                {
                    "Key": "BootstrapActionFilePath",
                    "Value": self.emr_sc_bootstrap_file_path,
                },
                {"Key": "StepConcurrencyLevel", "Value": self.emr_step_concurrency},
            ],
        )

        self.log.info("SC response: %s", response)
        if not response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            raise AirflowException("Service Catalog creation failed: %s" % response)
        else:
            self.log.info(
                "Service Catalog Stack with record id %s created",
                response["RecordDetail"]["RecordId"],
            )
            return (
                response["RecordDetail"]["RecordId"],
                response["RecordDetail"]["ProvisionedProductId"],
            )


class CreateEMRSensor(BaseSensorOperator):
    template_fields = ["provisioned_record_id", "aws_environment", "input_cluster_id"]
    template_ext = (".json",)

    @apply_defaults
    def __init__(
        self,
        *,
        conn_id="tesseract_aws_conn",
        aws_environment="dev-private",
        provisioned_record_id,
        input_cluster_id=None,
        **kwargs,
    ):
        if not provisioned_record_id:
            raise AirflowException(
                "Provisioned service catalog product's record id is required."
            )
        if "poke_interval" not in kwargs:
            kwargs["poke_interval"] = 5  # seconds
        super().__init__(**kwargs)
        self.conn_id = conn_id
        self.aws_environment = aws_environment
        self.provisioned_record_id = provisioned_record_id
        self.input_cluster_id = input_cluster_id
        self.target_states = ["SUCCEEDED"]
        self.failed_states = ["IN_PROGRESS_IN_ERROR", "FAILED"]

    """
    def get_boto3_sc_client(self):
        sc_hook = EDTAwsBaseHook(conn_id=self.conn_id, aws_environment=self.aws_environment)
        return sc_hook.get_client_type('servicecatalog')
    """

    def get_service_catalog_status(self):
        sc_client = AwsBaseHook(
            aws_conn_id=self.conn_id, client_type="servicecatalog"
        ).get_client_type("servicecatalog")
        self.log.info(
            "Poking service catalog provisioned product with record id %s",
            self.provisioned_record_id,
        )
        return sc_client.describe_record(Id=self.provisioned_record_id)

    def get_emr_cluster_status(self, context):
        emr_client = AwsBaseHook(
            aws_conn_id=self.conn_id, client_type="emr"
        ).get_client_type("emr")
        self.log.info(
            "Poking service catalog provisioned product with record id %s",
            self.provisioned_record_id,
        )
        try:
            response = emr_client.describe_cluster(ClusterId=self.input_cluster_id)
        except ClientError as e:
            message = e.response["Error"]["Message"]
            raise AirflowException(message)
        cluster_state = response.get("Cluster", {}).get("Status").get("State", "")
        if cluster_state in ["TERMINATING", "TERMINATED", "TERMINATED_WITH_ERRORS"]:
            message = f"cluster {self.input_cluster_id} is {cluster_state}"
            raise AirflowException(message)
        context["task_instance"].xcom_push(
            key="job_flow_id", value=self.input_cluster_id
        )
        return True

    @staticmethod
    def state_from_response(response):
        return response["RecordDetail"]["Status"]

    @staticmethod
    def failure_message_from_response(response):
        fail_details = response["RecordDetail"]["RecordErrors"]
        if fail_details:
            return "for reason(s) {}".format(fail_details)
        return None

    @staticmethod
    def get_cluster_id_from_response(response):
        outputs = response["RecordOutputs"]
        return next(
            (item for item in outputs if item["OutputKey"] == "ClusterId"), None
        )["OutputValue"]

    def poke(self, context):
        if self.input_cluster_id and self.input_cluster_id != "None":
            return self.get_emr_cluster_status(context)

        response = self.get_service_catalog_status()

        if not response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            self.log.info("Bad HTTP response: %s", response)
            return False

        state = self.state_from_response(response)
        self.log.info("Service catalog product currently %s", state)

        if state in self.target_states:
            cluster_id = self.get_cluster_id_from_response(response)
            context["task_instance"].xcom_push(key="job_flow_id", value=cluster_id)

            # restarting httpd for Ganglia
            try:
                if "Ganglia" in self.get_cluster_applications(cluster_id):
                    steps = [
                        {
                            "Name": "Ganglia - Restart httpd",
                            "ActionOnFailure": "CONTINUE",
                            "HadoopJarStep": {
                                "Jar": "command-runner.jar",
                                "Args": ["sudo", "systemctl", "restart", "httpd"],
                            },
                        }
                    ]
                    self.add_step(cluster_id, steps)
            except Exception as e:
                self.log.warning(e)
            return True

        if state in self.failed_states:
            # TODO: Delete the SC stack if creation failed
            final_message = "Service catalog provisioning failed"
            failure_message = self.failure_message_from_response(response)
            if failure_message:
                final_message += " " + failure_message
            raise AirflowException(final_message)

        return False

    def add_step(self, job_flow_id, steps, tries=1) -> dict:
        """
        Adds the EMr Step to cluster
        :param clusterid: EMR Cluster ID
        :type stepid: str: StepID
        :return: A dict contains all the transform job info
        """
        try:
            emr_hook = EmrHook(aws_conn_id=self.conn_id)
            emr = emr_hook.get_conn()
            return emr.add_job_flow_steps(JobFlowId=job_flow_id, Steps=steps)
        except ClientError as exception_obj:
            if exception_obj.response["Error"]["Code"] == "ThrottlingException":
                if tries <= 10:
                    print("Throttling Exception Occured while submitting the EMR Step.")
                    print("Retrying.....")
                    print("Attempt No.: " + str(tries))
                    time.sleep(30)
                    return self.add_step(job_flow_id, steps, tries + 1)
                else:
                    print("Attempted 3 Times But No Success.")
                    print("Raising Exception.....")
                    raise
            else:
                raise

    def get_cluster_applications(self, cluster_id) -> list:
        """
        Gets EMR cluster applications
        :param clusterid: EMR Cluster ID
        :return: A list of application names
        """
        emr_hook = EmrHook(aws_conn_id=self.conn_id)
        emr = emr_hook.get_conn()
        response = emr.describe_cluster(ClusterId=cluster_id)
        applications_dicts_list = response.get("Cluster", {}).get("Applications", [])
        applications = list(map(lambda x: x["Name"], applications_dicts_list))
        return applications


class TerminateEMROperator(BaseOperator):
    """
    Terminate an EMR cluster
    :param aws_conn_id: AWS airflow connection to use, leave null to use AWS default
    :type aws_conn_id: str
    :param region_name: AWS region name, defaulted to us-west-2
    :type region_name: str
    :param job_flow_id: EMR cluster id or job flow id e.g. j-17QAWMPZEL5AE
    :type job_flow_id: str
    """

    template_fields = ["aws_environment", "provisioned_product_id", "input_cluster_id"]
    template_ext = ()

    @apply_defaults
    def __init__(
        self,
        *,
        conn_id="tesseract_aws_conn",
        aws_environment="dev-private",
        provisioned_product_id,
        input_cluster_id=None,
        **kwargs,
    ):
        if not provisioned_product_id:
            raise AirflowException("Provisioned product id is required.")
        super().__init__(**kwargs)
        self.conn_id = conn_id
        self.aws_environment = aws_environment
        self.provisioned_product_id = provisioned_product_id
        self.input_cluster_id = input_cluster_id

    """
    def get_boto3_sc_client(self):
        sc_hook = EDTAwsBaseHook(conn_id=self.conn_id, aws_environment=self.aws_environment)
        return sc_hook.get_client_type('servicecatalog')
    """

    def execute(self, context):
        self.log.info(
            "Terminating SC provisioned product %s", self.provisioned_product_id
        )

        # If cluster id was given by user we cannot terminate via SC
        if self.input_cluster_id and self.input_cluster_id != "None":
            self.log.info(
                f"Cluster {self.input_cluster_id} was provided."
                f" cannot terminate via ServiceCatalog. Skipping.."
            )
            return

        # If product was not provisioned there is nothing to terminate
        if not self.provisioned_product_id:
            return

        sc_client = AwsBaseHook(
            aws_conn_id=self.conn_id, client_type="servicecatalog"
        ).get_client_type("servicecatalog")

        response = sc_client.terminate_provisioned_product(
            ProvisionedProductId=self.provisioned_product_id,
            IgnoreErrors=True,
        )

        if not response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            raise AirflowException(
                "Service catalog product termination failed: %s" % response
            )
        else:
            self.log.info(
                "Service catalog product with id %s terminated",
                self.provisioned_product_id,
            )
            self.log.info(
                "Service catalog Status %s ", response["RecordDetail"]["Status"]
            )

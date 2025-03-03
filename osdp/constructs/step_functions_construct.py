# step_functions_construct.py
from aws_cdk import BundlingFileAccess, Duration, Stack, triggers
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from aws_cdk import (
    aws_stepfunctions_tasks as sfn_tasks,
)
from constructs import Construct


class StepFunctionsConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        ecs_construct,
        data_bucket,
        collection_url,
        knowledge_base=None,
        data_source=None,
        knowledge_base_id=None,
        data_source_id=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id)

        # Create the ECS Run Task state
        run_task = sfn_tasks.EcsRunTask(
            self,
            "OsdpRunFargateManifestFetcherTask",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,  # Wait for task completion
            cluster=ecs_construct.cluster,
            task_definition=ecs_construct.task_definition,
            container_overrides=[
                sfn_tasks.ContainerOverride(
                    container_definition=ecs_construct.container,
                    environment=[
                        {
                            "name": "COLLECTION_URL",
                            "value": sfn.JsonPath.string_at("$.collection_url"),
                        },
                        {"name": "BUCKET_NAME", "value": data_bucket.bucket_name},
                    ],
                )
            ],
            assign_public_ip=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            launch_target=sfn_tasks.EcsFargateLaunchTarget(platform_version=ecs.FargatePlatformVersion.LATEST),
            propagated_tag_source=ecs.PropagatedTagSource.TASK_DEFINITION,
            result_path="$.task_result",  # I think this can be removed
        )

        # Lambda function for fetching manifests from url list
        fetch_iiif_manifest_function = _lambda.Function(
            self,
            "fetch_iiif_manifest_function",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=_lambda.Code.from_asset(
                "./functions/get_iiif_manifest",
                bundling={
                    "image": _lambda.Runtime.PYTHON_3_9.bundling_image,
                    "bundling_file_access": BundlingFileAccess.VOLUME_COPY,
                    "command": [
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                },
            ),
            timeout=Duration.minutes(2),
            environment={"BUCKET": data_bucket.bucket_name},
        )

        # Grant the Lambda function read/write access to S3
        data_bucket.grant_read(fetch_iiif_manifest_function)
        data_bucket.grant_put(fetch_iiif_manifest_function)

        # IAM Role for Step Functions to access S3 and invoke Lambda
        step_functions_role = iam.Role(
            self,
            "StepFunctionsExecutionRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )

        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket", "s3:GetObject"],
                resources=[
                    data_bucket.bucket_arn,
                    data_bucket.arn_for_objects("*"),
                ],
            )
        )

        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[fetch_iiif_manifest_function.function_arn],
            )
        )

        # Add permissions for the Step Function role
        step_functions_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:StartIngestionJob"], resources=["*"]))

        # Also add this permission
        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"], resources=[data_bucket.arn_for_objects("step-function-results/*")]
            )
        )

        # Lambda permission to allow invocation from Step Functions
        fetch_iiif_manifest_function.add_permission(
            "AllowStepFunctionsInvoke",
            principal=iam.ServicePrincipal("states.amazonaws.com"),
        )

        manifest_fetch_concurrency = self.node.try_get_context("manifest_fetch_concurrency") or 2

        # Define Distributed Map with ItemReader using a raw JSON state definition
        distributed_map_state = sfn.CustomState(
            self,
            "DistributedMapWithItemReader",
            state_json={
                "Type": "Map",
                "ItemReader": {
                    "Resource": "arn:aws:states:::s3:getObject",
                    "ReaderConfig": {"InputType": "CSV", "CSVHeaderLocation": "GIVEN", "CSVHeaders": ["uri"]},
                    "Parameters": {"Bucket.$": "$.s3.Bucket", "Key.$": "$.s3.Key"},
                },
                "MaxConcurrency": manifest_fetch_concurrency,
                "ItemProcessor": {
                    "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
                    "StartAt": "InvokeFetchManifest",
                    "States": {
                        "InvokeFetchManifest": {
                            "Type": "Task",
                            "Resource": "arn:aws:states:::lambda:invoke",
                            "Parameters": {
                                "FunctionName": fetch_iiif_manifest_function.function_arn,
                                "Payload": {
                                    "row.$": "$",
                                },
                            },
                            "TimeoutSeconds": 43200,  # 12 hours
                            "End": True,
                        }
                    },
                },
                "ResultWriter": {
                    "Resource": "arn:aws:states:::s3:putObject",
                    "Parameters": {"Bucket": data_bucket.bucket_name, "Prefix": "step-function-results/"},
                },
            },
        )

        # Add bedrock knowledge base ingestion task
        start_ingestion = sfn.CustomState(
            self,
            "StartBedrockIngestion",
            state_json={
                "Type": "Task",
                "Parameters": {
                    "DataSourceId": data_source_id,
                    "KnowledgeBaseId": knowledge_base_id,
                },
                "Resource": "arn:aws:states:::aws-sdk:bedrockagent:startIngestionJob",
            },
        )

        # Define the success and failure states
        success = sfn.Succeed(self, "TaskCompleted")
        _failure = sfn.Fail(self, "TaskFailed", error="TaskFailedError", cause="Task execution failed")

        definition = run_task.next(distributed_map_state).next(start_ingestion).next(success)

        self.state_machine = sfn.StateMachine(
            self, "OsdpStackSpinup", definition=definition, timeout=Duration.hours(12), role=step_functions_role
        )

        # Permissions are too broad for now
        # Use the Stack context to access account and region
        stack = Stack.of(self)
        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[f"arn:aws:states:{stack.region}:{stack.account}:stateMachine:*"],
            )
        )

        # Add a Lambda trigger for Step Functions execution
        self.step_function_trigger = triggers.TriggerFunction(
            self,
            "TriggerStepFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="index.handler",
            environment={
                "STATE_MACHINE_ARN": self.state_machine.state_machine_arn,
                "COLLECTION_URL": collection_url,
                "BUCKET": data_bucket.bucket_name,
                "KEY": "manifests.csv",
            },
            code=_lambda.Code.from_asset("./functions/step_function_trigger"),
            timeout=Duration.minutes(3),
            initial_policy=[
                iam.PolicyStatement(
                    actions=["states:StartExecution"],
                    resources=[self.state_machine.state_machine_arn],
                )
            ],
            execute_on_handler_change=False,
        )

        # Ensure the trigger function executes only after these resources are provisioned
        self.step_function_trigger.execute_after(self.state_machine)
        self.step_function_trigger.execute_after(data_bucket)
        self.step_function_trigger.execute_after(fetch_iiif_manifest_function)
        self.step_function_trigger.execute_after(knowledge_base)
        self.step_function_trigger.execute_after(data_source)

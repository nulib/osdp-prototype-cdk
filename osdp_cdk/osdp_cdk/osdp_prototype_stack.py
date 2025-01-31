import os

from aws_cdk import (
    CfnOutput,
    Duration,
    Fn,
    RemovalPolicy,
    Size,
    Stack,
    triggers,
)
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
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from aws_cdk import (
    aws_stepfunctions_tasks as sfn_tasks,
)
from aws_cdk import Tags
from constructs import Construct

ECR_REPO = "arn:aws:ecr:us-east-1:625046682746:repository/osdp-iiif-fetcher"
ECR_IMAGE = "625046682746.dkr.ecr.us-east-1.amazonaws.com/osdp-iiif-fetcher:latest"
COLLECTION_URL = os.getenv("COLLECTION_URL", "https://api.dc.library.northwestern.edu/api/v2/collections/819526ed-985c-4f8f-a5c8-631fc400c2f1?as=iiif")

class OsdpPrototypeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ✅ Apply tag to all resources in this stack
        Tags.of(self).add("project", "imls-grant")

        # Hello World Function
        # This is a standin for our API at the moment
        my_function = _lambda.Function(
            self, "HelloWorldFunction",
            runtime = _lambda.Runtime.NODEJS_20_X, # Provide any supported Node.js runtime
            handler = "index.handler",
            code = _lambda.Code.from_inline(
                """
                exports.handler = async function(event) {
                return {
                    headers: {
                        "Access-Control-Allow-Origin" : "*",
                        "Access-Control-Allow-Credentials" : true
                    },
                    statusCode: 200,
                    body: JSON.stringify('Hello World!'),
                };
                };
                """
            ),
        )

        # Define the Lambda function URL resource
        my_function_url = my_function.add_function_url(
            auth_type = _lambda.FunctionUrlAuthType.NONE,
        )

        # Define a CloudFormation output for your URL
        CfnOutput(self, "myFunctionUrlOutput", value=my_function_url.url)

        # S3 bucket for the static UI
        # Generate unique bucket name using the same logic as CloudFormation
        unique_id = Fn.select(2, Fn.split("/", self.stack_id))
        suffix = Fn.select(4, Fn.split("-", unique_id))
        ui_bucket_name = Fn.join("-", ["osdp-ui", suffix])

        # Create S3 bucket for the UI
        ui_bucket = s3.Bucket(
            self,
            "UserInterfaceBucket",
            bucket_name=ui_bucket_name,
            website_index_document="index.html",
            website_error_document="error.html",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Add bucket policy
        ui_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"{ui_bucket.bucket_arn}/*"],
                principals=[iam.AnyPrincipal()],
            )
        )

        # Output the website URL
        CfnOutput(
            self,
            "WebsiteURL",
            value=ui_bucket.bucket_website_url,
            description="URL for UI website hosted on S3",
        )

        # Lambda function to build the UI and deploy to S3
        build_function = triggers.TriggerFunction(
            self,
            "BuildFunction",
            runtime=_lambda.Runtime.NODEJS_LATEST,
            handler="index.handler",
            code=_lambda.Code.from_asset("./functions/build_function"),
            environment={
                "BUCKET_NAME": ui_bucket.bucket_name,
                "REPO_NAME": "osdp-prototype-ui",
                "NEXT_PUBLIC_API_URL": my_function_url.url,
            },
            timeout=Duration.minutes(5),
            memory_size=1024,
            ephemeral_storage_size=Size.gibibytes(1),
        )

        build_function.add_layers(
            _lambda.LayerVersion.from_layer_version_arn(
                self,
                "GitLayer",
                layer_version_arn="arn:aws:lambda:us-east-1:553035198032:layer:git-lambda2:8",
            )
        )

        build_function_url = build_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
        )

        CfnOutput(self, "buildFunctionUrl", value=build_function_url.url)

         # Grant Lambda permissions
        ui_bucket.grant_read_write(build_function)

        # S3 bucket for the IIIF Manifests
        manifest_bucket_name = Fn.join("-", ["osdp-manifests", suffix])

        manifest_bucket = s3.Bucket(
            self,
            "ManifestsBucket",
            bucket_name=manifest_bucket_name,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Use the default VPC
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # Create ECS Cluster
        cluster = ecs.Cluster(self, "OsdpCluster", vpc=vpc)

        # Task Role
        task_role = iam.Role(
            self,
            "OsdpTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"],
                resources=[ECR_REPO],
            )
        )

        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],  # This applies to the entire ECR service
            )
        )

        manifest_bucket.grant_put(task_role)

        # Execution Role for ECS Task
        execution_role = iam.Role(
            self,
            "OsdpExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],  # This allows getting auth tokens for ECR
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=[ECR_REPO],
            )
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=["*"],  # You can scope this to your log group ARN
            )
        )

        # Create Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            "OsdpIiifFetcherTaskDef",
            memory_limit_mib=512,
            cpu=256,
            task_role=task_role,
            execution_role=execution_role,
        )

        # Add container to task definition
        container = task_definition.add_container(
            "OsdpIiifFetcherContainer",
            image=ecs.ContainerImage.from_registry(ECR_IMAGE),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="osdp-iiif-fetcher",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
        )

        # Create the ECS Run Task state
        run_task = sfn_tasks.EcsRunTask(
            self,
            "OsdpRunFargateManifestFetcherTask",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,  # Wait for task completion
            cluster=cluster,
            task_definition=task_definition,
            container_overrides=[
                sfn_tasks.ContainerOverride(
                    container_definition=container,
                    environment=[
                        {
                            "name": "COLLECTION_URL",
                            "value": sfn.JsonPath.string_at("$.collection_url"),
                        },
                        {"name": "BUCKET_NAME", "value": manifest_bucket.bucket_name},
                    ],
                )
            ],
            assign_public_ip=True,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            launch_target=sfn_tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST
            ),
            propagated_tag_source=ecs.PropagatedTagSource.TASK_DEFINITION,
            result_path="$.task_result" # I think this can be removed
        )

        # Lambda function for processing orders
        fetch_iiif_manifest_function = _lambda.Function(
            self, "fetch_iiif_manifest_function",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=_lambda.Code.from_asset("./functions/get_iiif_manifest"),
            timeout=Duration.seconds(120)
        )

        # Grant the Lambda function read access to S3
        manifest_bucket.grant_read(fetch_iiif_manifest_function)

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
                    manifest_bucket.bucket_arn,  
                    manifest_bucket.arn_for_objects("*"),  
                ],
            )
        )

        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[fetch_iiif_manifest_function.function_arn],
            )
        )

        # Lambda permission to allow invocation from Step Functions
        fetch_iiif_manifest_function.add_permission(
            "AllowStepFunctionsInvoke",
            principal=iam.ServicePrincipal("states.amazonaws.com"),
        )

        # Define Distributed Map with ItemReader using a raw JSON state definition
        distributed_map_state = sfn.CustomState(
            self,
            "DistributedMapWithItemReader",
            state_json={
                "Type": "Map",
                "ItemReader": {
                    "Resource": "arn:aws:states:::s3:getObject",
                    "ReaderConfig": {
                        "InputType": "CSV",
                        "CSVHeaderLocation": "GIVEN",
                        "CSVHeaders": [
                            "uri"
                        ]
                    },
                    "Parameters": {
                        "Bucket.$": "$.s3.Bucket",  
                        "Key.$": "$.s3.Key"  
                    }
                },
                "MaxConcurrency": 1,
                "ItemProcessor": {
                    "ProcessorConfig": {
                        "Mode": "DISTRIBUTED",
                        "ExecutionType": "STANDARD"
                    },
                    "StartAt": "InvokeLambdaProcessor",
                    "States": {
                        "InvokeLambdaProcessor": {
                            "Type": "Task",
                            "Resource": "arn:aws:states:::lambda:invoke",
                            "Parameters": {
                                "FunctionName": fetch_iiif_manifest_function.function_arn,
                                "Payload": {
                                    "row": sfn.JsonPath.string_at("$$.Map.Item.Value")
                                }
                            },
                            "End": True
                        }
                    }
                }
            },
        )

        # First define the success and failure states
        success = sfn.Succeed(self, "TaskCompleted")
        _failure = sfn.Fail(self, "TaskFailed", error="TaskFailedError", cause="Task execution failed")

        definition = run_task.next(distributed_map_state).next(success)
        state_machine = sfn.StateMachine(
            self, "OsdpStackSpinup", 
            definition=definition,
            timeout=Duration.minutes(5),
            role=step_functions_role
        )

        # Permissions are too broad for now
        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[f"arn:aws:states:{self.region}:{self.account}:stateMachine:*"],
            )
        )

         # Add a Lambda trigger for Step Functions execution
        step_function_trigger = triggers.TriggerFunction(
            self,
            "TriggerStepFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="index.handler",
            environment={
                "STATE_MACHINE_ARN": state_machine.state_machine_arn,
                "COLLECTION_URL": COLLECTION_URL,
                "BUCKET": manifest_bucket.bucket_name,
                "KEY": "manifests.csv"
            },
            code=_lambda.Code.from_asset("./functions/step_function_trigger"),
            timeout=Duration.minutes(1),
            initial_policy=[
                iam.PolicyStatement(
                    actions=["states:StartExecution"],
                    resources=[state_machine.state_machine_arn],
                )
            ]
        )

        # Ensure trigger_function executes AFTER these resources are provisioned
        step_function_trigger.execute_after(state_machine)
        step_function_trigger.execute_after(manifest_bucket)
        step_function_trigger.execute_after(fetch_iiif_manifest_function)


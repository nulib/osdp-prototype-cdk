from typing import Optional

from aws_cdk import (
    Fn,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import aws_iam as iam
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct
from constructs.api_construct import ApiConstruct
from constructs.db_construct import DatabaseConstruct
from constructs.ecs_task_construct import EcsConstruct
from constructs.knowledge_base_construct import KnowledgeBaseConstruct
from constructs.step_functions_construct import StepFunctionsConstruct
from constructs.ui_construct import UIConstruct

ECR_IMAGE = "public.ecr.aws/nulib-staging/osdp-iiif-fetcher:latest"


class OsdpPrototypeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_prefix: str,
        ui_function_invoke_principal: Optional[iam.WebIdentityPrincipal] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Retrieve the 'tags' context value (expected to be a dict)
        # And apply to all resources in the stack
        context_tags = self.node.try_get_context("tags")
        if context_tags and isinstance(context_tags, dict):
            for key, value in context_tags.items():
                Tags.of(self).add(key, value)

        # Generate unique name logic
        unique_id = Fn.select(2, Fn.split("/", self.stack_id))
        suffix = Fn.select(4, Fn.split("-", unique_id))

        # S3 bucket for the IIIF Manifests (and other data)
        data_bucket_name = Fn.join("-", [self.stack_name.lower(), suffix])

        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name=data_bucket_name,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Instantiate the ECS construct
        ecs_construct = EcsConstruct(self, "EcsConstruct", data_bucket=data_bucket, ecr_image=ECR_IMAGE)

        # Database construct
        database_construct = DatabaseConstruct(self, "DatabaseConstruct")

        # Knowledge Base construct
        knowledge_base_construct = KnowledgeBaseConstruct(
            self,
            "KnowledgeBaseConstruct",
            data_bucket=data_bucket,
            embedding_model_arn=self.node.try_get_context("embedding_model_arn"),
            db_cluster=database_construct.db_cluster,
            db_credentials=database_construct.db_credentials,
            stack_prefix=stack_prefix,
            db_initialization=database_construct.db_init3_index,
        )

        # Create the API
        self.api_construct = ApiConstruct(
            self,
            "ApiConstruct",
            knowledge_base=knowledge_base_construct.knowledge_base,
            stack_prefix=stack_prefix,
            model_arn=self.node.try_get_context("foundation_model_arn"),
        )

        # Create the UI
        self.ui_construct = UIConstruct(
            self,
            "UIConstruct",
            stack_id=suffix,
            api_url=self.api_construct.api.url,
            cognito_user_pool=self.api_construct.user_pool,
            cognito_user_pool_id=self.api_construct.user_pool.user_pool_id,
            cognito_user_pool_client_id=self.api_construct.user_pool_client.user_pool_client_id,
            function_invoker_principal=ui_function_invoke_principal,
        )

        # Instantiate the Step Functions construct
        _step_functions_construct = StepFunctionsConstruct(
            self,
            "StepFunctionsConstruct",
            ecs_construct=ecs_construct,
            data_bucket=data_bucket,
            collection_url=self.node.try_get_context("collection_url"),
            knowledge_base=knowledge_base_construct.knowledge_base,  # Pass the actual construct
            data_source=knowledge_base_construct.s3_data_source,  # If you expose this
            db_cluster=database_construct.db_cluster,  # Pass DB cluster
            knowledge_base_id=knowledge_base_construct.knowledge_base_id,
            data_source_id=knowledge_base_construct.data_source_id,
        )

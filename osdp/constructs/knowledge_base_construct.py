#!/usr/bin/env python3
from aws_cdk import CfnOutput
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from constructs import Construct


class KnowledgeBaseConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        data_bucket: str,
        db_cluster: str,
        db_credentials: str,
        embedding_model_arn: str,
        stack_prefix: str,
        db_initialization: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Create IAM role for the Knowledge Base
        kb_role = iam.Role(
            self,
            "OsdpBedrockKBRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="IAM role for OSDP Bedrock Knowledge Base",
        )

        # Policy for S3 data source
        kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowS3Read",
                effect=iam.Effect.ALLOW,
                actions=["s3:*"],
                resources=[
                    data_bucket.bucket_arn,
                    data_bucket.arn_for_objects("*"),
                    data_bucket.arn_for_objects("iiif/*"),
                ],
            )
        )

        # RDS cluster policy for knowledgebase
        kb_role.add_to_policy(
            iam.PolicyStatement(actions=["rds:DescribeDBClusters"], resources=[db_cluster.cluster_arn])
        )

        # RDS data API policy for knowledgebase
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "rds-data:ExecuteStatement",
                    "rds-data:BatchExecuteStatement",
                ],
                resources=[db_cluster.cluster_arn],
            )
        )

        # Bedrock foundation model policy for knowledge base
        kb_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn]))

        # Secrets policy for knowldge base
        kb_role.add_to_policy(
            iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[db_credentials.secret_arn])
        )

        # Create the Knowledge Base
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "OsdpBedrockKB",
            name=f"{stack_prefix}-osdp-knowledge-base",
            role_arn=kb_role.role_arn,
            description="Knowledge base with S3 data source and Aurora PostgreSQL vector store",
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn,
                ),
            ),
            # Storage Configuration (Aurora PostgreSQL)
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="RDS",
                rds_configuration=bedrock.CfnKnowledgeBase.RdsConfigurationProperty(
                    credentials_secret_arn=db_credentials.secret_arn,
                    database_name="postgres",
                    resource_arn=db_cluster.cluster_arn,
                    table_name="bedrock_integration.bedrock_knowledge_base",
                    field_mapping=bedrock.CfnKnowledgeBase.RdsFieldMappingProperty(
                        metadata_field="metadata", primary_key_field="id", text_field="chunks", vector_field="embedding"
                    ),
                ),
            ),
        )

        self.s3_data_source = bedrock.CfnDataSource(
            self,
            "MyCfnDataSource",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=data_bucket.bucket_arn, inclusion_prefixes=["iiif/"]
                ),
            ),
            name="OsdpS3DataSource",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            description="OSDP S3 Data Source",
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=300, overlap_percentage=20
                    ),
                )
            ),
        )

        self.s3_data_source.node.add_dependency(self.knowledge_base)
        self.knowledge_base.node.add_dependency(kb_role)
        self.knowledge_base.node.add_dependency(db_cluster)
        self.knowledge_base.node.add_dependency(db_credentials)
        self.knowledge_base.node.add_dependency(db_initialization)

        # Add these properties to expose IDs
        self.knowledge_base_id = self.knowledge_base.attr_knowledge_base_id
        self.data_source_id = self.s3_data_source.attr_data_source_id

        CfnOutput(self, "KnowledgeBaseId", value=self.knowledge_base.attr_knowledge_base_id)
        CfnOutput(self, "KnowledgeBaseRoleArn", value=kb_role.role_arn)

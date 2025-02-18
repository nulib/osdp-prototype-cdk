#!/usr/bin/env python3
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_rds as rds,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_s3 as s3,
    custom_resources as cr,
    aws_ec2 as ec2,
    Fn,
    Token,
    aws_bedrock as bedrock

)
from constructs import Construct

class KBStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/cohere.embed-multilingual-v3"

        # Import the DB cluster attributes from the DatabaseStack via CloudFormation exports
        db_cluster = rds.DatabaseCluster.from_database_cluster_attributes(
            self,
            "ImportedDBCluster",
            cluster_identifier=Fn.import_value("DatabaseClusterIdentifier"),
            cluster_endpoint_address=Fn.import_value("DatabaseEndpoint"),
            port=Token.as_number(Fn.import_value("DatabasePort")),
            security_groups=[]
        )

        # Import the DB credentials secret
        db_credentials = secretsmanager.Secret.from_secret_complete_arn(
            self,
            "ImportedDBSecret",
            secret_complete_arn=Fn.import_value("DatabaseSecretArn")
        )

        # TODO - pass this. For now, look up the data bucket by name
        data_bucket = s3.Bucket.from_bucket_name(self, "DataBucket", "kdid-osdp-prototype-0e4075a57531")

        # Create IAM role for the Knowledge Base
        kb_role = iam.Role(
            self, "OsdpBedrockKBRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="IAM role for OSDP Bedrock Knowledge Base"
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
                    data_bucket.arn_for_objects("iiif/*")
                ],
            )
        )

        # RDS cluster policy for knowledgebase
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rds:DescribeDBClusters"
            ],
            resources=[
                db_cluster.cluster_arn
            ]
        ))

        # RDS data API policy for knowledgebase
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rds-data:ExecuteStatement",
                "rds-data:BatchExecuteStatement",
            ],
            resources=[
                db_cluster.cluster_arn
            ]
        ))


        # Bedrock foundation model policy for knowledge base
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel"
            ],
            resources=[MODEL_ARN]
        ))

        # Secrets policy for knowldge base
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue"
                ],
                resources=[
                    db_credentials.secret_arn
                ]
            )
        )

        # Create the Knowledge Base
        knowledge_base = bedrock.CfnKnowledgeBase(
            self, "OsdpBedrockKB",
            name="osdp-knowledge-base",
            role_arn=kb_role.role_arn,
            description="Knowledge base with S3 data source and Aurora PostgreSQL vector store",
            
            # Knowledge Base Configuration
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn="arn:aws:bedrock:us-east-1::foundation-model/cohere.embed-multilingual-v3",
                    
                    # S3 configuration
                    supplemental_data_storage_configuration=bedrock.CfnKnowledgeBase.SupplementalDataStorageConfigurationProperty(
                        supplemental_data_storage_locations=[
                            bedrock.CfnKnowledgeBase.SupplementalDataStorageLocationProperty(
                                supplemental_data_storage_location_type="S3",
                                s3_location=bedrock.CfnKnowledgeBase.S3LocationProperty(
                                    uri=f"s3://{data_bucket.bucket_name}/"  # TODO Replace 
                                )
                            )
                        ]
                    )
                )
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
                        metadata_field="metadata",
                        primary_key_field="id",
                        text_field="chunks",
                        vector_field="embedding"
                    )
                )
            )
        )

        knowledge_base.node.add_dependency(kb_role)
        knowledge_base.node.add_dependency(db_cluster)
        knowledge_base.node.add_dependency(db_credentials)

        # Add dependencies to ensure proper ordering
        # knowledge_base.node.add_dependency(db_init3_index)
        # knowledge_base.node.add_dependency(db_cluster)

        # These for dev
        # CfnOutput(self, "DatabaseEndpoint", value=db_cluster.cluster_endpoint.hostname)
        # CfnOutput(self, "DatabasePort", value=str(db_cluster.cluster_endpoint.port))
        # CfnOutput(self, "VpcId", value=vpc.vpc_id)
        CfnOutput(self, "KnowledgeBaseId", value=knowledge_base.attr_knowledge_base_id)

        # CfnOutput(self, "DatabaseClusterArn", value=db_cluster.cluster_arn)
        # CfnOutput(self, "DatabaseSecretArn", value=db_credentials.secret_arn)
        CfnOutput(self, "KnowledgeBaseRoleArn", value=kb_role.role_arn)


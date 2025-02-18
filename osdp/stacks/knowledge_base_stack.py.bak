#!/usr/bin/env python3
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import aws_iam as iam
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_s3 as s3
from aws_cdk import custom_resources as cr


from constructs import Construct


class BedrockKnowledgeBaseStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/cohere.embed-multilingual-v3"

        # Instantiate a Bedrock Knowledge Base CloudFormation resource.
        # This configuration uses:
        #   - S3 as the data source (implied by setting type="S3" so that the default parser and chunking are used)
        #   - Aurora PostgreSQL Serverless (via an RDS configuration) as the vector store
        #   - The Coher Embed Multilingual V3 embedding model

        # Use the default VPC
        vpc = ec2.Vpc.from_lookup(
            self, "DefaultVPC",
            is_default=True
        )

        # Create security group for the Aurora cluster
        db_security_group = ec2.SecurityGroup(
            self, "OsdpDatabaseSecurityGroup",
            vpc=vpc,
            description="Security group for OSDP Aurora PostgreSQL cluster",
            allow_all_outbound=False
        )

        # Add necessary inbound rule for Bedrock
        db_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description="Allow Bedrock to connect to PostgreSQL"
        ),

        # Create database credentials in Secrets Manager
        db_credentials = secretsmanager.Secret(
            self, "OsdpDBCredentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "postgres"}',
                generate_string_key="password",
                exclude_characters="\"@/\\"
            )
        )

        # Create Aurora Serverless v2 cluster
        db_cluster = rds.DatabaseCluster(
            self,"OsdpKnowledgeBaseDB",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_3 # Version?
            ),
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            security_groups=[db_security_group],
            credentials=rds.Credentials.from_secret(db_credentials),
            removal_policy=RemovalPolicy.DESTROY, # TODO Change this for production
            serverless_v2_min_capacity=0.5,  # Minimum ACU (Aurora Capacity Units)
            serverless_v2_max_capacity=1,     # Maximum ACU for dev
            enable_data_api=True,
        )

        # Configure the cluster for Bedrock
        db_init = cr.AwsCustomResource(
            self, "DBInit",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": db_cluster.cluster_arn,
                    # Split into separate statements for better error handling
                    "sql": """
                        CREATE EXTENSION IF NOT EXISTS vector;
                    """,
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-1")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["rds-data:ExecuteStatement"],
                    resources=[db_cluster.cluster_arn]
                ),
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db_credentials.secret_arn]
                )
            ])
        )

        # Create schema
        db_init2_schema = cr.AwsCustomResource(
            self, "DBInit2Schema",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": db_cluster.cluster_arn,
                    "sql": "CREATE SCHEMA IF NOT EXISTS bedrock_integration;"
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-2-Schema")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["rds-data:ExecuteStatement"],
                    resources=[db_cluster.cluster_arn]
                ),
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db_credentials.secret_arn]
                )
            ])
        )

        # Create role with password
        db_init2_role = cr.AwsCustomResource(
                    self, "DBInit2Role",
                    on_create=cr.AwsSdkCall(
                        service="RDSDataService",
                        action="executeStatement",
                        parameters={
                            "secretArn": db_credentials.secret_arn,
                            "database": "postgres",
                            "resourceArn": db_cluster.cluster_arn,
                            "sql": f"""
                                    DO $$ 
                                    BEGIN 
                                        CREATE ROLE bedrock_user WITH LOGIN PASSWORD '{db_credentials.secret_value_from_json('password').unsafe_unwrap()}'; 
                                    EXCEPTION WHEN duplicate_object THEN 
                                        RAISE NOTICE 'Role already exists'; 
                                    END $$;
                                """
                        },
                        physical_resource_id=cr.PhysicalResourceId.of("DBInit-2-Role")
                    ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["rds-data:ExecuteStatement"],
                    resources=[db_cluster.cluster_arn]
                ),
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db_credentials.secret_arn]
                )
            ])
        )

        # Grant permissions
        db_init2_grant = cr.AwsCustomResource(
            self, "DBInit2Grant",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": db_cluster.cluster_arn,
                    "sql": "GRANT ALL ON SCHEMA bedrock_integration TO bedrock_user;"
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-2-Grant")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["rds-data:ExecuteStatement"],
                    resources=[db_cluster.cluster_arn]
                ),
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db_credentials.secret_arn]
                )
            ])
        )

        # Add dependencies
        db_init2_schema.node.add_dependency(db_init)
        db_init2_role.node.add_dependency(db_init2_schema)
        db_init2_grant.node.add_dependency(db_init2_role)

        # Create table and index

        # Create table
        db_init3_table = cr.AwsCustomResource(
            self, "DBInit3Table",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": db_cluster.cluster_arn,
                    "sql": """
                        CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_knowledge_base (
                            id uuid PRIMARY KEY,
                            embedding vector(384),
                            chunks text,
                            metadata jsonb
                        );
                    """
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-3-Table")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["rds-data:ExecuteStatement"],
                    resources=[db_cluster.cluster_arn]
                ),
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db_credentials.secret_arn]
                )
            ])
        )

        # Create index
        db_init3_index = cr.AwsCustomResource(
            self, "DBInit3Index",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": db_cluster.cluster_arn,
                    "sql": """
                        CREATE INDEX IF NOT EXISTS embedding_idx ON bedrock_integration.bedrock_knowledge_base 
                            USING hnsw (embedding vector_l2_ops);
                    """
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-3-Index")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["rds-data:ExecuteStatement"],
                    resources=[db_cluster.cluster_arn]
                ),
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[db_credentials.secret_arn]
                )
            ])
        )

        # Add dependencies to ensure proper order
        db_init3_table.node.add_dependency(db_init2_grant)
        db_init3_index.node.add_dependency(db_init3_table)

        # Ensure proper dependency order
        db_init.node.add_dependency(db_cluster)

        # TODO - pass this. For now, look up the data bucket by name
        data_bucket = s3.Bucket.from_bucket_name(self, "DataBucket", "kdid-osdp-prototype-0afffd87bcb1")

        # Create IAM role for the Knowledge Base
        kb_role = iam.Role(
            self, "OsdpBedrockKBRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="IAM role for OSDP Bedrock Knowledge Base"
        )

        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket", "s3:GetObject"],
                resources=[
                    data_bucket.bucket_arn,  
                    data_bucket.arn_for_objects("*"),  
                ],
            )
        )

        # Add permissions for RDS (Aurora PostgreSQL)
        # kb_role.add_to_policy(iam.PolicyStatement(
        #     actions=[
        #         "rds-db:connect",
        #         "rds:*",  # Full RDS permissions
        #         "rds-data:*",  # Full RDS Data API permissions
        #     ],
        #     resources=["*"]  # Temporarily allow all resources to debug
        # ))
        
        # Add permissions for RDS (Aurora PostgreSQL)
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rds:DescribeDBClusters",
                "rds:DescribeDBInstances",
                "rds-data:ExecuteStatement",
                "rds-data:BatchExecuteStatement",
                "rds-data:BeginTransaction",
                "rds-data:CommitTransaction",
                "rds-data:RollbackTransaction",
            ],
            resources=[
                db_cluster.cluster_arn,  
                f"{db_cluster.cluster_arn}/*", 
            ]
        ))

        # Add any other necessary permissions for Bedrock
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel"
            ],
            resources=[MODEL_ARN]
        ))

        # Add Secrets Manager permissions
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[
                    db_credentials.secret_arn,
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:*" # remove, excessive
                ]
            )
        )

        # Create the Knowledge Base
        # knowledge_base = bedrock.CfnKnowledgeBase(
        #     self, "OsdpBedrockKB",
        #     name="osdp-knowledge-base",
        #     role_arn=kb_role.role_arn,
        #     description="Knowledge base with S3 data source and Aurora PostgreSQL vector store",
            
        #     # Knowledge Base Configuration
        #     knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
        #         type="VECTOR",
        #         vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
        #             embedding_model_arn="arn:aws:bedrock:us-east-1::foundation-model/cohere.embed-multilingual-v3",
                    
        #             # S3 configuration
        #             supplemental_data_storage_configuration=bedrock.CfnKnowledgeBase.SupplementalDataStorageConfigurationProperty(
        #                 supplemental_data_storage_locations=[
        #                     bedrock.CfnKnowledgeBase.SupplementalDataStorageLocationProperty(
        #                         supplemental_data_storage_location_type="S3",
        #                         s3_location=bedrock.CfnKnowledgeBase.S3LocationProperty(
        #                             uri=f"s3://{data_bucket.bucket_name}/"  # TODO Replace 
        #                         )
        #                     )
        #                 ]
        #             )
        #         )
        #     ),

            # Storage Configuration (Aurora PostgreSQL)
            # storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
            #     type="RDS",
            #     rds_configuration=bedrock.CfnKnowledgeBase.RdsConfigurationProperty(
            #         credentials_secret_arn=db_credentials.secret_arn,
            #         database_name="osdp-knowledgebase",  
            #         resource_arn=db_cluster.cluster_arn,
            #         table_name="embeddings",  
            #         field_mapping=bedrock.CfnKnowledgeBase.RdsFieldMappingProperty(
            #             metadata_field="metadata",
            #             primary_key_field="id",
            #             text_field="text",
            #             vector_field="embedding"
            #         )
            #     )
            # )
        # )

        # Add dependencies to ensure proper ordering
        # knowledge_base.node.add_dependency(db_init)
        # knowledge_base.node.add_dependency(db_cluster)

        # These for dev
        CfnOutput(self, "DatabaseEndpoint", value=db_cluster.cluster_endpoint.hostname)
        CfnOutput(self, "DatabasePort", value=str(db_cluster.cluster_endpoint.port))
        CfnOutput(self, "VpcId", value=vpc.vpc_id)
        # CfnOutput(self, "KnowledgeBaseId", value=knowledge_base.attr_knowledge_base_id)

        CfnOutput(self, "DatabaseClusterArn", value=db_cluster.cluster_arn)
        CfnOutput(self, "DatabaseSecretArn", value=db_credentials.secret_arn)
        CfnOutput(self, "KnowledgeBaseRoleArn", value=kb_role.role_arn)
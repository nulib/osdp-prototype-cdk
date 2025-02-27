from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_rds as rds,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from aws_cdk import (
    custom_resources as cr,
)
from constructs import Construct


class DatabaseConstruct(Construct):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Use the default VPC
        vpc = ec2.Vpc.from_lookup(self, "DefaultVPC", is_default=True)

        # Create security group for the Aurora cluster
        db_security_group = ec2.SecurityGroup(
            self,
            "OsdpDatabaseSecurityGroup",
            vpc=vpc,
            description="Security group for OSDP Aurora PostgreSQL cluster",
            allow_all_outbound=False,
        )

        # Add necessary inbound rule for Bedrock
        (
            db_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(5432),
                description="Allow Bedrock to connect to PostgreSQL",
            ),
        )

        # Create database credentials in Secrets Manager
        self.db_credentials = secretsmanager.Secret(
            self,
            "OsdpDBCredentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "postgres"}',
                generate_string_key="password",
                exclude_characters='"@/\\',
            ),
        )

        # Create Aurora Serverless v2 cluster
        self.db_cluster = rds.DatabaseCluster(
            self,
            "OsdpKnowledgeBaseDB",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_3  # Version?
            ),
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[db_security_group],
            credentials=rds.Credentials.from_secret(self.db_credentials),
            removal_policy=RemovalPolicy.DESTROY,  # TODO Change this for production
            serverless_v2_min_capacity=0.5,  # Minimum ACU (Aurora Capacity Units)
            serverless_v2_max_capacity=1,  # Maximum ACU for dev
            enable_data_api=True,
        )

        # Configure the cluster for Bedrock
        db_init = cr.AwsCustomResource(
            self,
            "DBInit",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": self.db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": self.db_cluster.cluster_arn,
                    # Split into separate statements for better error handling
                    "sql": """
                        CREATE EXTENSION IF NOT EXISTS vector;
                    """,
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-1"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(actions=["rds-data:ExecuteStatement"], resources=[self.db_cluster.cluster_arn]),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"], resources=[self.db_credentials.secret_arn]
                    ),
                ]
            ),
        )

        # Create schema
        db_init2_schema = cr.AwsCustomResource(
            self,
            "DBInit2Schema",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": self.db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": self.db_cluster.cluster_arn,
                    "sql": "CREATE SCHEMA IF NOT EXISTS bedrock_integration;",
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-2-Schema"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(actions=["rds-data:ExecuteStatement"], resources=[self.db_cluster.cluster_arn]),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"], resources=[self.db_credentials.secret_arn]
                    ),
                ]
            ),
        )

        # Create role with password
        db_password = self.db_credentials.secret_value_from_json("password").unsafe_unwrap()

        db_init2_role = cr.AwsCustomResource(
            self,
            "DBInit2Role",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": self.db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": self.db_cluster.cluster_arn,
                    "sql": f"""
                                    DO $$ 
                                    BEGIN 
                                        CREATE ROLE bedrock_user WITH LOGIN PASSWORD '{db_password}'; 
                                    EXCEPTION WHEN duplicate_object THEN 
                                        RAISE NOTICE 'Role already exists'; 
                                    END $$;
                                """,
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-2-Role"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(actions=["rds-data:ExecuteStatement"], resources=[self.db_cluster.cluster_arn]),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"], resources=[self.db_credentials.secret_arn]
                    ),
                ]
            ),
        )

        # Grant permissions
        db_init2_grant = cr.AwsCustomResource(
            self,
            "DBInit2Grant",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": self.db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": self.db_cluster.cluster_arn,
                    "sql": "GRANT ALL ON SCHEMA bedrock_integration TO bedrock_user;",
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-2-Grant"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(actions=["rds-data:ExecuteStatement"], resources=[self.db_cluster.cluster_arn]),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"], resources=[self.db_credentials.secret_arn]
                    ),
                ]
            ),
        )

        # Add dependencies
        db_init2_schema.node.add_dependency(db_init)
        db_init2_role.node.add_dependency(db_init2_schema)
        db_init2_grant.node.add_dependency(db_init2_role)

        # Create table and index

        # Create table
        db_init3_table = cr.AwsCustomResource(
            self,
            "DBInit3Table",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": self.db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": self.db_cluster.cluster_arn,
                    "sql": """
                        CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_knowledge_base (
                            id uuid PRIMARY KEY,
                            embedding vector(1024),
                            chunks text,
                            metadata jsonb
                        );
                    """,
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-3-Table"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(actions=["rds-data:ExecuteStatement"], resources=[self.db_cluster.cluster_arn]),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"], resources=[self.db_credentials.secret_arn]
                    ),
                ]
            ),
        )

        # Create index
        self.db_init3_index = cr.AwsCustomResource(
            self,
            "DBInit3Index",
            on_create=cr.AwsSdkCall(
                service="RDSDataService",
                action="executeStatement",
                parameters={
                    "secretArn": self.db_credentials.secret_arn,
                    "database": "postgres",
                    "resourceArn": self.db_cluster.cluster_arn,
                    "sql": """
                        CREATE INDEX IF NOT EXISTS embedding_idx ON bedrock_integration.bedrock_knowledge_base 
                            USING ivfflat (embedding vector_l2_ops);
                    """,
                },
                physical_resource_id=cr.PhysicalResourceId.of("DBInit-3-Index"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(actions=["rds-data:ExecuteStatement"], resources=[self.db_cluster.cluster_arn]),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"], resources=[self.db_credentials.secret_arn]
                    ),
                ]
            ),
        )

        # Add dependencies to ensure proper order
        db_init3_table.node.add_dependency(db_init2_grant)
        self.db_init3_index.node.add_dependency(db_init3_table)

        # Ensure proper dependency order
        db_init.node.add_dependency(self.db_cluster)

        CfnOutput(self, "DatabaseClusterArn", value=self.db_cluster.cluster_arn)
        CfnOutput(self, "DatabaseClusterIdentifier", value=self.db_cluster.cluster_identifier)
        CfnOutput(self, "DatabaseEndpoint", value=self.db_cluster.cluster_endpoint.hostname)
        CfnOutput(self, "DatabasePort", value=str(self.db_cluster.cluster_endpoint.port))
        CfnOutput(self, "DatabaseSecretArn", value=self.db_credentials.secret_arn)

import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest
from stacks.osdp_prototype_stack import OsdpPrototypeStack


@pytest.fixture
def stack_and_template():
    app = core.App()
    app.node.set_context("stack_prefix", "alice")
    app.node.set_context("tags", {"foo": "bar", "environment": "dev"})
    app.node.set_context("data", {"type": "iiif", "collection_url": "http://example.com"})
    app.node.set_context(
        "embedding_model_arn", "arn:aws:sagemaker:us-east-1:123456789012:model/bedrock-embedding-model"
    )
    app.node.set_context(
        "foundation_model_arn", "arn:aws:sagemaker:us-east-1:123456789012:model/bedrock-embedding-model"
    )
    app.node.set_context("aws:cdk:bundling-stacks", [])  # Disable bundling to speed up tests
    stack = OsdpPrototypeStack(app, "alice-OSDP-Prototype", env={"account": "123456789012", "region": "us-east-1"})
    template = assertions.Template.from_stack(stack)
    return stack, template


def test_aurora_cluster_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::RDS::DBCluster",
        {
            "Engine": "aurora-postgresql",
            "EngineVersion": assertions.Match.string_like_regexp("16.6"),
            "ServerlessV2ScalingConfiguration": {"MinCapacity": 0.5, "MaxCapacity": 8},
            "EnableHttpEndpoint": True,
        },
    )


def test_db_security_group_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "GroupDescription": assertions.Match.string_like_regexp(".*OSDP.*PostgreSQL.*"),
            "SecurityGroupIngress": [
                {
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "IpProtocol": "tcp",
                    "Description": assertions.Match.string_like_regexp(".*Bedrock.*"),
                }
            ],
        },
    )


def test_db_credentials_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {
            "GenerateSecretString": {
                "SecretStringTemplate": '{"username": "postgres"}',
                "GenerateStringKey": "password",
                "ExcludeCharacters": '"@/\\',
            }
        },
    )

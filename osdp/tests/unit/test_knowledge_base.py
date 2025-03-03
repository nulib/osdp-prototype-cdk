import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest
from stacks.osdp_prototype_stack import OsdpPrototypeStack


@pytest.fixture
def stack_and_template():
    app = core.App()
    app.node.set_context("stack_prefix", "alice")
    app.node.set_context("tags", {"foo": "bar", "environment": "dev"})
    app.node.set_context("collection_url", "http://example.com")
    app.node.set_context(
        "embedding_model_arn", "arn:aws:sagemaker:us-east-1:123456789012:model/bedrock-embedding-model"
    )
    app.node.set_context(
        "foundation_model_arn", "arn:aws:sagemaker:us-east-1:123456789012:model/bedrock-embedding-model"
    )

    app.node.set_context("aws:cdk:bundling-stacks", [])  # Disable bundling to speed up tests
    stack = OsdpPrototypeStack(
        app, "alice-OSDP-Prototype", stack_prefix="alice", env={"account": "123456789012", "region": "us-east-1"}
    )
    template = assertions.Template.from_stack(stack)
    return stack, template


def test_knowledge_base_outputs(stack_and_template):
    stack, template = stack_and_template

    # Get ALL outputs
    all_outputs = template.find_outputs("*")
    print("All outputs:", list(all_outputs.keys()))

    # Filter manually
    kb_id_outputs = [k for k in all_outputs.keys() if "KnowledgeBaseId" in k]
    kb_role_outputs = [k for k in all_outputs.keys() if "KnowledgeBaseRoleArn" in k]

    print("ID outputs found:", kb_id_outputs)
    print("Role outputs found:", kb_role_outputs)

    assert len(kb_id_outputs) > 0, "No KnowledgeBaseId output found"
    assert len(kb_role_outputs) > 0, "No KnowledgeBaseRoleArn output found"


def test_knowledge_base_resource_created(stack_and_template):
    stack, template = stack_and_template
    template.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)


def test_data_source_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::Bedrock::DataSource", {"Name": "OsdpS3DataSource", "Description": "OSDP S3 Data Source"}
    )

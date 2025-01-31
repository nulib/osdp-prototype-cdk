import pytest
import aws_cdk as core
import aws_cdk.assertions as assertions

from osdp_cdk.osdp_prototype_stack import OsdpPrototypeStack

@pytest.fixture
def stack_template():
    app = core.App()
    stack = OsdpPrototypeStack(app, "OsdpPrototypeStack")
    template = assertions.Template.from_stack(stack)
    return template  # Return the template object directly

def test_ui_bucket_created():
    stack_template.has_resource_properties("AWS::S3::Bucket", {
        "BucketName": "osdp-ui-bucket"
    })

    stack_template.has_output("WebsiteURL", {
        "Value": "osdp-ui-bucket.s3-website-us-east-1.amazonaws.com"
    })

def test_build_function_created():
    stack_template.has_resource_properties("AWS::Lambda::Function", {
        "FunctionName": "BuildFunction"
    })

def test_build_function_triggers_created():
    stack_template.has_resource_properties("AWS::Events::Rule", {
        "EventPattern": {
            "Source": ["aws.events"]
        }
    })






import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

from osdp_cdk.osdp_prototype_stack import OsdpPrototypeStack


@pytest.fixture
def stack_template():
    app = core.App()
    stack = OsdpPrototypeStack(app, "OsdpPrototypeStack",env={
        "account": "123456789012",  
        "region": "us-east-1"  
    })
    template = assertions.Template.from_stack(stack)
    return template  

def test_ui_bucket_created(stack_template):  
    stack_template.has_resource_properties("AWS::S3::Bucket", {
        "WebsiteConfiguration": {} 
    })

    stack_template.has_output("WebsiteURL", {
        "Description": "URL for UI website hosted on S3",
        "Value": {
            "Fn::GetAtt": assertions.Match.array_with([
                assertions.Match.string_like_regexp("UserInterface.*"),
                "WebsiteURL"
            ])
        }
    })

def test_build_function_created(stack_template):  
    stack_template.has_resource_properties("AWS::Lambda::Function", {
        "Handler": "index.handler",
        "Runtime": "nodejs18.x",
        "Layers": ["arn:aws:lambda:us-east-1:553035198032:layer:git-lambda2:8"], "Timeout": 300, 
        "MemorySize": 1024,
        "EphemeralStorage": {
            "Size": 1024 
        },
        "Environment": {
            "Variables": {
                "BUCKET_NAME": assertions.Match.any_value(),
                "REPO_NAME": "osdp-prototype-ui",
                "NEXT_PUBLIC_API_URL": assertions.Match.any_value()
            }
        }
    })

def test_manifest_bucket_created(stack_template):
    stack_template.has_resource_properties("AWS::S3::Bucket", {
        "BucketName": {
            "Fn::Join": [
                "-",
                [
                    "osdp-manifests",
                    assertions.Match.any_value()
                ]
            ]
        }
    })

def test_task_role_created(stack_template):
    stack_template.has_resource_properties("AWS::IAM::Role", {
        "AssumeRolePolicyDocument": {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"}
                }
            ]
        }
    })

def test_execution_role_created(stack_template):
    stack_template.has_resource_properties("AWS::IAM::Role", {
        "AssumeRolePolicyDocument": {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"}
                }
            ]
        }
    })

def test_cluster_created(stack_template):
    stack_template.has_resource_properties("AWS::ECS::Cluster", {})

def test_task_definition_created(stack_template):
    stack_template.has_resource_properties("AWS::ECS::TaskDefinition", {
        "ContainerDefinitions": [
            {
                "Name": "OsdpIiifFetcherContainer"
            }
        ]
    }) 

def test_state_machine_created(stack_template):
    stack_template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    










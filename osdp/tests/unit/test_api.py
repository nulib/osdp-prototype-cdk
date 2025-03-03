import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest
from stacks.osdp_prototype_stack import OsdpPrototypeStack

STACK_PREFIX = "alice"


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
        app, "alice-OSDP-Prototype", stack_prefix=STACK_PREFIX, env={"account": "123456789012", "region": "us-east-1"}
    )
    template = assertions.Template.from_stack(stack)
    return stack, template


def test_cognito_user_pool_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "UserPoolName": f"{STACK_PREFIX}-OSDPUsers",
            "AutoVerifiedAttributes": ["email"],
            "MfaConfiguration": "OFF",
            "Policies": {
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": True,
                    "RequireUppercase": True,
                }
            },
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
        },
    )


def test_cognito_user_pool_client_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "UserPoolId": assertions.Match.any_value(),
            "ClientName": f"{STACK_PREFIX}-OSDPClient",
            "ExplicitAuthFlows": [
                "ALLOW_USER_PASSWORD_AUTH",
                "ALLOW_ADMIN_USER_PASSWORD_AUTH",
                "ALLOW_USER_SRP_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
            ],
            "PreventUserExistenceErrors": "ENABLED",
            "EnableTokenRevocation": True,
        },
    )


def test_admin_group_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::Cognito::UserPoolGroup",
        {
            "GroupName": "Admin",
            "UserPoolId": assertions.Match.any_value(),
        },
    )


def test_chat_lambda_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "index.handler",
            "Runtime": "python3.11",
            "Timeout": 120,
            "Environment": {
                "Variables": {
                    "KNOWLEDGE_BASE_ID": assertions.Match.any_value(),
                    "MODEL_ARN": assertions.Match.any_value(),
                }
            },
        },
    )


def test_api_gateway_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::ApiGateway::RestApi",
        {
            "Name": "alice-OSDP-API",
        },
    )


def test_api_gateway_cors_configured(stack_and_template):
    stack, template = stack_and_template
    response_headers = {
        "ResponseParameters": {
            "method.response.header.Access-Control-Allow-Headers": assertions.Match.string_like_regexp(".*"),
            "method.response.header.Access-Control-Allow-Methods": assertions.Match.string_like_regexp(".*POST.*"),
        }
    }
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {
            "HttpMethod": "OPTIONS",
            "ResourceId": assertions.Match.any_value(),
            "RestApiId": assertions.Match.any_value(),
            "Integration": {
                "IntegrationResponses": assertions.Match.array_with([assertions.Match.object_like(response_headers)]),
            },
        },
    )


def test_chat_endpoint_with_cognito_auth(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {
            "HttpMethod": "POST",
            "ResourceId": assertions.Match.any_value(),
            "RestApiId": assertions.Match.any_value(),
            "AuthorizationType": "COGNITO_USER_POOLS",
            "AuthorizerId": assertions.Match.any_value(),
            "Integration": {
                "Type": "AWS_PROXY",
                "IntegrationHttpMethod": "POST",
            },
        },
    )


def test_lambda_has_bedrock_permissions(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Action": [
                                    "bedrock:InvokeModel",
                                    "bedrock:Retrieve",
                                    "bedrock:RetrieveAndGenerate",
                                    "bedrock:GetInferenceProfile",
                                ],
                                "Effect": "Allow",
                            }
                        )
                    ]
                )
            }
        },
    )

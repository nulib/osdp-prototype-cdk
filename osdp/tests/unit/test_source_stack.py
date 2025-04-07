import aws_cdk as core
import aws_cdk.assertions as assertions
import aws_cdk.aws_iam as iam
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


def test_ui_amplify_created(stack_and_template):
    stack, template = stack_and_template

    template.has_resource_properties(
        "AWS::Amplify::App",
        {
            "Name": {
                "Fn::Join": [
                    "-",
                    [
                        assertions.Match.string_like_regexp(f"{stack.stack_name.lower()}-ui"),
                        assertions.Match.any_value(),
                    ],
                ]
            }
        },
    )

    template.has_output(
        "*",
        {
            "Description": "URL for UI hosted on Amplify",
            "Value": assertions.Match.object_like(
                {
                    "Fn::Join": [
                        "",
                        [
                            "https://main.",  # main branch hardcoded in ui construct
                            {
                                "Fn::GetAtt": assertions.Match.array_with(
                                    [assertions.Match.string_like_regexp("AmplifyApp.*"), "DefaultDomain"]
                                )
                            },
                        ],
                    ]
                }
            ),
        },
    )


def test_build_function_created(stack_and_template):
    stack, template = stack_and_template

    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "index.handler",
            "Runtime": "nodejs22.x",
            "Layers": ["arn:aws:lambda:us-east-1:553035198032:layer:git-lambda2:8"],
            "Timeout": 600,
            "MemorySize": 1024,
            "EphemeralStorage": {"Size": 10240},
            "Environment": {
                "Variables": {
                    "AMPLIFY_APP_ID": {
                        "Fn::GetAtt": [
                            assertions.Match.string_like_regexp("AmplifyApp.*"),
                            "AppId",
                        ],
                    },
                    "AMPLIFY_BRANCH_NAME": assertions.Match.any_value(),
                    "REPO_NAME": "osdp-prototype-ui",
                    "NEXT_PUBLIC_API_URL": assertions.Match.any_value(),
                }
            },
        },
    )


def test_function_invoker_role_not_created(stack_and_template):
    stack, template = stack_and_template

    template.resource_properties_count_is(
        "AWS::IAM::Role",
        {
            "RoleName": f"{stack.stack_name}-UIBuildFunctionInvokerRole",
        },
        0,
    )


def test_function_invoker_role_created():
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
    github_action_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    principal = iam.WebIdentityPrincipal(
        github_action_arn,
        conditions={"StringLike": {"token.actions.githubusercontent.com:sub": "repo:nulib/osdp-prototype-ui:*"}},
    )
    stack = OsdpPrototypeStack(
        app,
        "alice-OSDP-Prototype",
        ui_function_invoke_principal=principal,
        env={"account": "123456789012", "region": "us-east-1"},
    )
    template = assertions.Template.from_stack(stack)

    template.resource_properties_count_is(
        "AWS::IAM::Role",
        {
            "RoleName": f"{stack.stack_name}-UIBuildFunctionInvokerRole",
        },
        1,
    )


def test_manifest_bucket_created(stack_and_template):
    stack, template = stack_and_template
    expected_stack_name = stack.stack_name.lower()

    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": {"Fn::Join": ["-", [expected_stack_name, assertions.Match.any_value()]]}}
    )


def test_task_role_created(stack_and_template):
    stack, template = stack_and_template

    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}}]
            }
        },
    )


def test_execution_role_created(stack_and_template):
    stack, template = stack_and_template

    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}}]
            }
        },
    )


def test_cluster_created(stack_and_template):
    stack, template = stack_and_template

    template.has_resource_properties("AWS::ECS::Cluster", {})


def test_task_definition_created(stack_and_template):
    stack, template = stack_and_template
    template.has_resource_properties(
        "AWS::ECS::TaskDefinition", {"ContainerDefinitions": [{"Name": "OsdpIiifFetcherContainer"}]}
    )


def test_state_machine_created(stack_and_template):
    stack, template = stack_and_template

    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

# ui_construct.py
from typing import Optional

from aws_cdk import BundlingFileAccess, BundlingOptions, CfnOutput, Duration, Size, Stack, triggers
from aws_cdk import aws_amplify_alpha as amplify
from aws_cdk import aws_iam as iam
from aws_cdk import (
    aws_lambda as _lambda,
)
from constructs import Construct


class UIConstruct(Construct):
    """
    Construct for the OSDP UI hosted on AWS Amplify.

    This construct creates an Amplify app and branch, and a Lambda function to build and deploy the UI.

    Attributes:
        amplify_app (amplify.App): The Amplify app created by this construct.
        amplify_branch (amplify.Branch): The Amplify branch created by this construct.
        build_function (_lambda.Function): The Lambda function that builds and deploys the UI.
        build_function_url (str): The URL for the build function.
        function_invoker_role (Optional[iam.Role]): The role that can invoke the build function.

    Args:
        scope (Construct): The parent construct.
        id (str): The construct ID.
        stack_id (str): The unique ID for the stack.
        api_url (str): The URL of the API to be included in the UI build.
        function_invoker_principal (Optional[iam.IPrincipal]): Principal that can invoke the build function.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        amplify_app: amplify.App,
        api_url: str,
        cognito_user_pool: None,
        cognito_user_pool_id: str,
        cognito_user_pool_client_id: str,
        function_invoker_principal: Optional[iam.IPrincipal] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id)

        stack = Stack.of(self)
        app_branch_name = "main"

        self.amplify_branch = amplify_app.add_branch(app_branch_name, stage="PRODUCTION")

        self.build_function = triggers.TriggerFunction(
            self,
            "BuildFunction",
            runtime=_lambda.Runtime.NODEJS_22_X,
            handler="index.handler",
            code=_lambda.Code.from_asset(
                "./functions/build_function",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.NODEJS_22_X.bundling_image,
                    bundling_file_access=BundlingFileAccess.VOLUME_COPY,
                    user="root",
                    command=["bash", "-c", "npm i && cp -r . /asset-output/"],
                ),
            ),
            environment={
                "REPO_NAME": "osdp-prototype-ui",
                "NEXT_PUBLIC_API_URL": api_url,
                "NEXT_PUBLIC_COGNITO_USER_POOL_ID": cognito_user_pool_id,
                "NEXT_PUBLIC_COGNITO_USER_POOL_CLIENT_ID": cognito_user_pool_client_id,
                "AMPLIFY_APP_ID": amplify_app.app_id,
                "AMPLIFY_BRANCH_NAME": app_branch_name,
            },
            timeout=Duration.minutes(10),
            memory_size=1024,
            ephemeral_storage_size=Size.gibibytes(1),
            initial_policy=[
                iam.PolicyStatement(
                    actions=["amplify:CreateDeployment", "amplify:StartDeployment"],
                    resources=[
                        self.amplify_branch.arn,
                        f"{self.amplify_branch.arn}/*",
                    ],
                )
            ],
            execute_on_handler_change=False,
        )

        # Add the Git layer to the build function
        self.build_function.add_layers(
            _lambda.LayerVersion.from_layer_version_arn(
                self,
                "GitLayer",
                layer_version_arn="arn:aws:lambda:us-east-1:553035198032:layer:git-lambda2:8",
            )
        )

        self.build_function_url = self.build_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.AWS_IAM,
        )

        self.function_invoker_role = None
        if function_invoker_principal:
            self.function_invoker_role = iam.Role(
                self,
                "UIBuildFunctionInvokeRole",
                # Allow the principal to assume the role
                assumed_by=function_invoker_principal,
                # Role names must be unique within an account
                # so prepend the stack name, which includes the stack prefix
                role_name=f"{stack.stack_name}-UIBuildFunctionInvokerRole",
            )

            self.function_invoker_role.attach_inline_policy(
                iam.Policy(
                    self,
                    "UIBuildFunctionInvokerPolicy",
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[self.build_function.function_arn],
                        )
                    ],
                )
            )

            self.build_function.add_permission(
                "UIBuildFunctionInvokerPermission",
                principal=iam.ArnPrincipal(self.function_invoker_role.role_arn),
                action="lambda:InvokeFunction",
            )

        self.build_function.node.add_dependency(amplify_app)
        self.build_function.node.add_dependency(cognito_user_pool)

        CfnOutput(self, "buildFunctionUrl", value=self.build_function_url.url)
        CfnOutput(
            self,
            "Website URL",
            value=f"https://{app_branch_name}.{amplify_app.default_domain}",
            description="URL for UI hosted on Amplify",
        )
        CfnOutput(
            self,
            "BuildFunctionInvokerRoleArn",
            value=self.function_invoker_role.role_arn if self.function_invoker_role else "N/A",
            description="The ARN of the role that can invoke the build function.",
        )
        CfnOutput(
            self,
            "BuildFunctionInvokerRoleName",
            value=self.function_invoker_role.role_name if self.function_invoker_role else "N/A",
            description="The name of the role that can invoke the build function.",
        )

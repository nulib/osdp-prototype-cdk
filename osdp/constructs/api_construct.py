from typing import List

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_amplify_alpha as amplify
from aws_cdk import (
    aws_apigateway as apigw,
)
from aws_cdk import (
    aws_cognito as cognito,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from constructs import Construct


class ApiConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        knowledge_base: str,
        stack_prefix: str,
        model_arn: str,
        amplify_app: amplify.App,
        allowed_origins: List[str],  # Add this parameter
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Create a Cognito User Pool
        self.user_pool = cognito.UserPool(
            self,
            "OSDPUsers",
            user_pool_name=f"{stack_prefix}-OSDPUsers",
            self_sign_up_enabled=False,  # Only admin can create users
            auto_verify={"email": True},
            password_policy=cognito.PasswordPolicy(
                min_length=8, require_lowercase=True, require_digits=True, require_symbols=True, require_uppercase=True
            ),
            sign_in_case_sensitive=False,
            mfa=cognito.Mfa.OFF,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create a User Pool Client
        self.user_pool_client = self.user_pool.add_client(
            "OSDPClient",
            user_pool_client_name=f"{stack_prefix}-OSDPClient",
            auth_flows={"user_password": True, "admin_user_password": True, "user_srp": True},
            prevent_user_existence_errors=True,
            enable_token_revocation=True,
        )

        # Create an Admin Group in the User Pool
        _admin_group = cognito.CfnUserPoolGroup(
            self, "AdminPoolGroup", user_pool_id=self.user_pool.user_pool_id, group_name="Admin"
        )

        # Stack outputs
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)

        # Create chat function integration
        chat_function = _lambda.Function(
            self,
            "ChatFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_asset("./functions/chat"),
            timeout=Duration.minutes(2),
            memory_size=1024,
            environment={"KNOWLEDGE_BASE_ID": knowledge_base.attr_knowledge_base_id, "MODEL_ARN": model_arn},
        )

        chat_function.node.add_dependency(knowledge_base)

        self.region = Stack.of(self).region
        self.account = Stack.of(self).account

        # Add Bedrock permissions
        chat_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate",
                    "bedrock:GetInferenceProfile",
                ],
                resources=[  # TODO - scope these better
                    model_arn,
                    f"arn:aws:bedrock:{self.region}:{self.account}:model/*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/*",
                    "arn:aws:bedrock:*:*:foundation-model/*",
                ],
            )
        )

        # Create Cognito Authorizer
        auth = apigw.CognitoUserPoolsAuthorizer(self, "ChatAuthorizer", cognito_user_pools=[self.user_pool])

        # Create API Gateway
        self.api = apigw.RestApi(
            self,
            "OSDPApi",
            rest_api_name=f"{stack_prefix}-OSDP-API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
                status_code=200,
                allow_methods=["OPTIONS", "POST"],
                allow_origins=["*"],
            ),
            endpoint_configuration=apigw.EndpointConfiguration(types=[apigw.EndpointType.REGIONAL]),
        )

        # Add /chat route with Cognito authorization
        chat_integration = apigw.LambdaIntegration(chat_function)
        chat_resource = self.api.root.add_resource("chat")
        chat_resource.add_method(
            "POST", chat_integration, authorizer=auth, authorization_type=apigw.AuthorizationType.COGNITO
        )

        self.api.node.add_dependency(self.user_pool)
        self.api.node.add_dependency(knowledge_base)
        self.api.node.add_dependency(amplify_app)

        # Add API Gateway URL to outputs
        CfnOutput(self, "ApiUrl", value=self.api.url)

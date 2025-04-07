from aws_cdk import Stage
from aws_cdk import aws_iam as iam
from constructs import Construct
from stacks.osdp_prototype_stack import OsdpPrototypeStack


class OsdpApplicationStage(Stage):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        github_action_arn = f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com"

        principal = iam.WebIdentityPrincipal(
            github_action_arn,
            conditions={"StringLike": {"token.actions.githubusercontent.com:sub": "repo:nulib/osdp-prototype-ui:*"}},
        )

        OsdpPrototypeStack(self, "OSDP-Prototype", ui_function_invoke_principal=principal)

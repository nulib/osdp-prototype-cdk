from aws_cdk import Stage

from constructs import Construct
from stacks.osdp_prototype_stack import OsdpPrototypeStack


class OsdpApplicationStage(Stage):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        github_action_arn = f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com"

        stack = OsdpPrototypeStack(self, "OSDP-Prototype", ui_function_invoke_arn=github_action_arn)

        if stack.ui_construct.function_invoker_principal:
            # For staging deploy, restrict the function to only be invoked by our GitHub Action
            stack.ui_construct.function_invoker_principal.with_conditions(
                {
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": "repo:nulib/osdp-prototype-ui:*"
                    }
                }
            )

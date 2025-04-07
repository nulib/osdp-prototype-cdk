#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import SecretValue, pipelines
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from pipeline.osdp_application_stage import OsdpApplicationStage


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the CodePipeline source
        source = pipelines.CodePipelineSource.git_hub(
            "nulib/osdp-prototype-cdk",
            "main",
            authentication=SecretValue.secrets_manager("osdp/github-token"),
        )

        # Get stack_prefix and other configs from parameter store
        # The parameter in SSM contains the complete CLI parameters string
        config_param = ssm.StringParameter.from_string_parameter_name(self, "ConfigParam", "/osdp/staging/config")

        # Define the synth step.
        # Use the parameter value directly from SSM
        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",
                "pip install uv",
                "sudo dnf install -y libxcrypt-compat || true",
                "uv sync --no-dev",
                ". .venv/bin/activate",
                "cd osdp",
                "cdk --version",
                "cdk synth $(node -e \"console.log(process.env.CONFIG_PARAM || '')\")",
            ],
            primary_output_directory="osdp/cdk.out",
            env={"CONFIG_PARAM": config_param.string_value},
        )

        # Define the CodePipeline using CDK Pipelines
        pipeline = pipelines.CodePipeline(
            self,
            "OsdpPipeline",
            synth=synth,
        )

        validation_wave = pipeline.add_wave("Validation")

        validation_wave.add_pre(
            pipelines.ShellStep(
                "Lint",
                input=source,
                commands=["pip install uv", "uv sync --only-dev", ". .venv/bin/activate", "ruff check ."],
            )
        )

        validation_wave.add_pre(
            pipelines.ShellStep(
                "Style",
                input=source,
                commands=["pip install uv", "uv sync --only-dev", ". .venv/bin/activate", "ruff format --check ."],
            )
        )

        validation_wave.add_pre(
            pipelines.ShellStep(
                "Test",
                input=source,
                commands=[
                    "npm install -g aws-cdk",
                    "pip install uv",
                    "uv sync",
                    ". .venv/bin/activate",
                    "cd osdp",
                    "pytest -vv tests/",
                ],
            )
        )

        # Define the application stages
        # The stack_prefix will be passed through the context by the synth step
        deploy_stage = OsdpApplicationStage(
            self, "staging", env=cdk.Environment(account="625046682746", region="us-east-1")
        )
        pipeline.add_stage(deploy_stage)

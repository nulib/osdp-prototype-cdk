#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import SecretValue, pipelines
from constructs import Construct
from pipeline.osdp_application_stage import OsdpApplicationStage


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, stack_prefix: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the CodePipeline source
        source = pipelines.CodePipelineSource.git_hub(
            "nulib/osdp-prototype-cdk",
            "main",
            authentication=SecretValue.secrets_manager("osdp/github-token"),
        )

        # Define the synth step.
        # Pass the context parameters including stack_prefix set to "staging".
        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",
                "pip install uv",
                "uv sync --no-dev",
                "cd osdp",
                "cdk --version",
                f"cdk synth -c stack_prefix={stack_prefix}",
            ],
            primary_output_directory="osdp/cdk.out",
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
                commands=["pip install uv", "uv sync --only-dev", "ruff check ."],
            )
        )

        validation_wave.add_pre(
            pipelines.ShellStep(
                "Style",
                input=source,
                commands=["pip install uv", "uv sync --only-dev", "ruff format --check ."],
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
                    "cd osdp",
                    "pytest -vv tests/",
                ],
            )
        )

        # Define the application stages
        deploy_stage = OsdpApplicationStage(
            self, "staging", stack_prefix=stack_prefix, env=cdk.Environment(account="625046682746", region="us-east-1")
        )
        pipeline.add_stage(deploy_stage)


# OSDP Prototype

## Quick start 🚀

### Prerequisites

To get started you will need to have the following installed:

- `uv` ([installation instructions](https://github.com/astral-sh/uv))
- AWS cdk cli (see [install instructions)](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html))

> [!NOTE]
> If you don't have `uv` installed (or don't want to), see [alternate instructions](#install-uv-with-python) below.

### Install

Run the following commands:

```bash
uv venv
uv sync
```

### Deploy

Run the deploy command with a required `stack_prefix`:

```bash
cd osdp && cdk deploy -c stack_prefix=my_awesome_stack
```

### Install `uv` with Python

To install `uv` locally

Ensure you are using Python 3.10:

```bash
python --version
# Python 3.10.5
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install `uv` within the virutual environment:

```bash
pip install uv
```

Install dependencies:

```bash
uv sync
```

## Development 🛠️

### IIIF manifest fetcher docker image

This is a ECR repository that is consumed by the OSDP.

See its [readme](iiif/README.md) for more information.

### OSDP Prototype Stack (CDK)

#### Setup

The OSDP primarily uses Python, but NodeJS is used for one lambda.

##### Python

Follow steps 0-3 in the [quickstart](#quick-start-)

> [!TIP]
> If using VSCode, set your Python interpreter by opening the Command Palette `⇧⌘P` and choosing `Python: Select Interpreter`.
> Set the path to `./.venv/bin/python`.
> Read more [here](https://code.visualstudio.com/docs/python/environments#_working-with-python-interpreters).


##### Node

Ensure using v22:

```bash
node --version
# v22.13.1
```

There is one lambda that uses node:

```bash
cd functions/build_function
npm i
cd ../../
```

#### Define context values

Context values are key-value pairs that can be associated with an app, stack, or construct. They may be supplied in the `cdk.json` or or on the command line.

Since the `cdk.json` file is generally committed to source control, it should generally be used for values shared with the team. Anything that needs to be overriden with specific deploys should be supplied on theh command line.

##### Required context values

- `stack_prefix` (str) - will be appended to the beginning of the CloudFormation stack on deploy. (*For NU devs this is not needed, it will use the `DEV_PREFIX` env var in AWS.)
- `collection_url` (str)- the url of the IIIF collection to load during deployment. There is a small collection (6 items) in the `cdk.json` file, but you will want to change or override on the command line.
- `embedding_model_arn` (str) - Embedding model to use for Bedrock Knowledgebase
- `foundation_model_arn` (str) - Foundation model to use for Bedrock RetreiveAndGenerate invocations

##### Optional context values

- `tags` (dict) - Key value pair tags applied to all resources in the stack. Example:
```
"tags": {
      "project": "chatbot"
    },
```
- `manifest_fetch_url` (str) - The concurrency to use when retrieving IIIF manifests from your API. If not provided, the default will be used (2).

```bash
# use default secret name (`OSDPSecrets`)
cdk deploy
```

#### Providing context values on the command line

Example:
```
cdk deploy -c stack_prefix=alice
```

#### Synthesize the CloudFormation template (optional)

Synthesize the CloudFormation template for this code (login to AWS account first). You must first log in to AWS with administrator credentials.

```bash
cdk synth
```

#### Deploy the CDK app

To deploy the stack to AWS. You must first log in to AWS with administrator credentials using `aws sso login`.

First obtain your stack name. Ex:
```bash
cdk ls

yourprefix-OSDP-Prototype #this one is your stack name
OsdpPipelineStack
OsdpPipelineStack/staging/OSDP-Prototype (staging-OSDP-Prototype)
```

Then deploy your stack:

```bash
cdk deploy yourprefix-OSDP-Prototype
```


#### Testing

To run the tests.

```bash
pytest
```

If the app has not been synthesized, tests may fail. See [synth instructions](#synthesize-the-cloudformation-template-optional).

#### Linting

```bash
ruff check .
```

or

```bash
ruff check --fix .
```

#### Style

To run formatting

```bash
ruff format .
```

## Useful commands

Useful `cdk` commands to be run within the `osdp/` directory:

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!

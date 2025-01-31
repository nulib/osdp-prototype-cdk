
# OSDP Prototype Stack (CDK)


### Setup

The `cdk.json` file tells the CDK Toolkit how to execute your app.

To manually create a virtualenv

```
$ python3 -m venv .venv
```

Aactivate your virtualenv.

```
$ source .venv/bin/activate
```

Install the required dependencies.

```
$ pip install -r requirements.txt requirements-dev.txt
```

Synthesize the CloudFormation template for this code (login to AWS account first).

```
$ cdk synth
```

To deploy the stack to AWS.

```
$ cdk deploy
``` 

### Testing

To run the tests.

```
$ pytest
```

### Style 

```
$ ruff check .
```

or 

```
$ ruff check --fix .
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!

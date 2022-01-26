
# Organizational Cloudtrail Event Notification

This project creates a notification system for cloudtrail events being logged to a cloudwatch log group. 

It does this by creating cloudwatch metric-filters and alarms on patterns in your logs, along with an eventbridge rule to for the state changes of those alarms, and a lambda function which then gathers details of the cloudwatch log entry and sends notification to a Slack Channel and SNS topic of your choosing.

This system can be very effective for monitoring a whole AWS Organization of accounts when utilizing an organization cloudtrail and logging that trail to a cloudwatch log group. Alarm patterns will be matched against events in all the accounts in your organization automatically and send notifications centrally within minutes. 

## Prerequisites and Bootstrapping

You need to have a cloudwatch log group enabled on a cloudtrail you wish to monitor.  
You must prestage a slack webhook url into secret manager in the same region where your stack will be deployed it should have the format:

- secret key: "url"
- secret value: "https://hooks.slack.com/services/foo/bar"

## Installation

This is an aws CDK project in Python and uses the standard `cdk deploy` to deploy this application as a cloudformation stack in your aws account. It will create all the necessary resources in AWS except for the cloudwatch log group and the slack secret.

### Configuration

Configuration of parameters for this project are kept in the `cdk.json` file, which tells the CDK Toolkit how to execute your app. Replace the `log_group_name` `slack_secret_name` and `subscribers` list in the cdk.json file to customize this app for your environment. New rules and alerts can be added anytime to the `alerts` block. Changes will need to be re-deployed. 

### Build and Deploy

We've included a [Taskfile](https://github.com/adriancooney/Taskfile) to simplify the setup, build and deploy of this cdk project. Taskfile is like a makefile but is natively a set of shell functions, and doesnt require any special dependencies.
To see the functions provided execute:

```bash
./Taskfile
```

### Initial Setup

```bash
./Taskfile setup
```

This will create the virtualenv for python, install the dependencies for cdk and the lambda, and then create the lambda layer zip file.

### Deploy

```bash
./Taskfile deploy
```

This will do a synthesis of the cdk stack and attempt to deploy it to the account your are currently logged into.

If you make configuration changes and/or add new alert patterns, re-execute `./Taskfile deploy` and the cloudformation stack will apply a changeset and make updates.

### Teardown

To remove this stack and clean up all resources (except the secret) just execute:

```bash
cdk destroy
```

Alternatively you can delete the cloudformation stack in the console or by cli. 

from typing import Any, Dict, List, Tuple
from webbrowser import get
import aws_lambda_powertools as alp
import os
import json
import boto3
from datetime import date, datetime,timezone,timedelta
from aws_lambda_powertools.utilities.parameters import get_secret
from aws_lambda_powertools.utilities.data_classes import event_source, EventBridgeEvent
from slack_sdk.webhook import WebhookClient, WebhookResponse

## Lambda IAM role permissions needed:
# secrets_manager.get_secret
# cloudwatch.describe_metric_filters
# cloudwatch.filter_log_events
# organizations.list_accounts
# sns.publish

## Lambda Env Variables
# Required:
#   SLACK_SECRET -- AWS SecretManager name of secret
#   LOG_GROUP -- cloudwatch log group name we are monitoring
# Optional:
#   LOG_LEVEL -- logging setting 
#   INTERVAL -- how far back in minutes to filter logs
#   SNS_TOPIC_ARN -- the sns topic to publish on

# globals
log_level = os.environ.get("LOG_LEVEL", "INFO")
interval = float(os.environ.get("INTERVAL", 5))
logger = alp.Logger("alarm-notifier", level=log_level)
sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
cloudtrail_log_group = os.environ.get("LOG_GROUP", "cloudtrail_log_group")
metric_namespace = os.environ.get("NAMESPACE", "CloudTrail Alert Metrics")

def get_past_time(minutes_interval: float=10) -> int:
    dt = datetime.now(timezone.utc)- timedelta(minutes=minutes_interval) 
    return int(dt.timestamp()*1000)

# we retrieve the log event that triggered the alarm
def get_cloudtrail_log_event(alarm_name: str, namespace: str) -> Dict[str,Any]:
    start_time = get_past_time(interval)
    # convert to epoch m
    cwlogs = boto3.client('logs')
    # get the filter pattern for the alarm that fired (assumes they are named the same)
    response = cwlogs.describe_metric_filters(metricNamespace=namespace,metricName=alarm_name)
    if response['metricFilters']:
        logger.debug("Getting MetricFilter Pattern")
        filter_pattern = response['metricFilters'][0]['filterPattern']
        logger.debug(filter_pattern)
        # now get all the events matching that filter in the past x mintures
        response = cwlogs.filter_log_events(
            logGroupName = cloudtrail_log_group,
            filterPattern = filter_pattern,
            startTime = start_time,
        )
        logs = response.get('events', list())  # event.message is a str has to be converted to dict. 
        if logs:
            newest = logs[-1]
            return json.loads(newest.get('message', ""))
    return dict()

def get_account_metadata(account_id: str) -> Tuple[str, str]:
    client = boto3.client('organizations')
    response = client.list_accounts()
    for account in response['Accounts']:
        if account_id == account.get('Id'):
            return ( account.get('Name'), account.get('Email'))
    return ("", "")

def format_msg(alarm_name: str, alarm_description: str, log_event: str)  -> Dict[str,Any]:
    #log_event = json.loads(event_msg)
    event_info= dict()
    event_info['alarm'] = alarm_name
    event_info['description'] = alarm_description
    acct_id = log_event.get('userIdentity').get('accountId')
    acct_name, acct_email = get_account_metadata(acct_id)
    event_info["account"] = {
        'id': acct_id,
        'name': acct_name,
        'email': acct_email
    }
    event_info['user']={
        'name': log_event.get('userIdentity').get('userName'),
        'type': log_event.get('userIdentity').get('type'),
        'key': log_event.get('userIdentity').get('accessKeyId')
    }
    event_info['event']={
        'name': log_event.get('eventName'),
        'source': log_event.get('eventSource'),
        'region': log_event.get('awsRegion'),
        'time': log_event.get('eventTime')
    }
    return event_info

def send_sns(topic_arn: str, info: dict) -> dict:
    sns = boto3.client('sns', region_name="us-gov-west-1")
    subject = f"ALERT! The cloudtrail {info['alarm']} alarm has been activated!"
    message = subject + "\n"+ info['description']+"\n"
    message+= "Source Account:\n" + json.dumps(info['account'],indent=4) +"\n"
    message+= "User Info:\n" + json.dumps(info['user'], indent=4)+'\n'
    message+= "Event Info:\n" + json.dumps(info['event'],indent=4)+"\n"
    resp = sns.publish(
        TopicArn=topic_arn,
        Message=message,
        Subject=subject
    )
    return resp

def send_slack(client: WebhookClient, info: dict) -> WebhookResponse: 
    emoji = ":warning:"
    msg_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{info['alarm']} triggered on {info['event']['name']}*"
            }
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"_{info['description']}_"
        }
        },
        {
            "type": "divider",
        },
        {
			"type": "section",
			"fields": [
                {
                    "type": "mrkdwn",
					"text": f"*Acct Name: {info['account']['name']}*"
                },
                {
                    "type": "mrkdwn",
					"text": f"*Region: {info['event']['region']}*"
                },
                {
					"type": "mrkdwn",
					"text": f"*Acct ID: #-{info['account']['id'][-4:]}*"
				}, 
                {
					"type": "mrkdwn",
					"text": f"*Root Email: {info['account']['email']}*"
				}, 

    
            ]
        },

        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"User: *{info['user']['name']}* executed _{info['event']['name']}_ on service _{info['event']['source']}_ at *{info['event']['time']}*"
            }
        },


    ]
    response: WebhookResponse = client.send(text= f"{emoji} *Alarm {info['alarm']}*",blocks=msg_blocks)
    return response

# lambda request handler
@logger.inject_lambda_context(log_event=True)
@event_source(data_class=EventBridgeEvent)
def handle_request(event: EventBridgeEvent, context: Dict[str,Any]):
    alarm_name = event.detail['alarmName']
    alarm_description = event.detail['configuration']['description']
    slack_url = get_secret(os.environ.get("SLACK_SECRET", "aws_status_slack_webhook"), transform="json")['url']
    slack_client = WebhookClient(slack_url)
    log_event = get_cloudtrail_log_event(alarm_name, metric_namespace)
    if log_event:
        logger.debug("matching event found, sending notifications")
        logger.debug(log_event)
        info = format_msg(alarm_name, alarm_description, log_event)
        if sns_topic_arn != "":
            send_sns(sns_topic_arn, info)
        send_slack(slack_client, info)
    else:
        logger.debug("No matching event found")
from distutils.command.config import config
import dotenv
from lambdas import alarm_notifier
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from dotenv import dotenv_values
from slack_sdk.webhook import WebhookClient

test_iam_log = {
    "eventVersion" : "1.0",
    "userIdentity": {
        "type": "IAMUser",
        "principalId": "EX_PRINCIPAL_ID",
        "arn": "arn:aws:iam::123456789012:user/Alice",
        "accountId": "123456789012",
        "accessKeyId": "EXAMPLE_KEY_ID",
        "userName": "Alice"
    },
    "eventTime": "2014-03-24T21:11:59Z",
    "eventSource": "iam.amazonaws.com",
    "eventName": "CreateUser",
    "awsRegion": "us-east-2",
    "sourceIPAddress": "127.0.0.1",
    "userAgent": "aws-cli/1.3.2 Python/2.7.5 Windows/7",
    "requestParameters": {"userName": "Bob"},
    "responseElements": {
        "user": {
            "createDate": "Mar 24, 2014 9:11:59 PM",
            "userName": "Bob",
            "arn": "arn:aws:iam::123456789012:user/Bob",
            "path": "/",
            "userId": "EXAMPLEUSERID"
        }
    }
}

def mock_get_account_metadata(account_id:str):
    return ('anaccount', 'root@anaccount.com')

def lambda_context():
    @dataclass
    class LambdaContext:
        function_name: str = "test"
        memory_limit_in_mb: int = 128
        invoked_function_arn: str = "arn:aws:lambda:us-gov-west-1:123456789012:function:test"
        aws_request_id: str = "52fdfc07-2182-154f-163f-5f0f9a621d72"

    return LambdaContext()

def test_get_since_time():
    interval = 15
    now = int(datetime.now(timezone.utc).timestamp()*1000)
    ago = alarm_notifier.get_past_time(interval)
    assert (now-ago)==interval*60*1000

def test_format_message():
    alarm_name = "test_alarm"
    alarm_notifier.get_account_metadata = mock_get_account_metadata
    info = alarm_notifier.format_msg(alarm_name,test_iam_log)
    assert info['account']['id'] == '089226552368'
    assert info['user']['name'] =='Alice'

def test_send_slack():
    config = dotenv_values()
    assert "SLACK_URL" in config.keys()
    slack_url = config['SLACK_URL']
    alarm_notifier.get_account_metadata = mock_get_account_metadata
    info = alarm_notifier.format_msg("test-alarm",test_iam_log)
    wc = WebhookClient(slack_url)
    resp = alarm_notifier.send_slack(wc, info)
    assert resp.status_code == 200

def test_send_sns():
    config = dotenv_values()
    assert "SNS_TOPIC_ARN" in config.keys()
    sns_arn = config['SNS_TOPIC_ARN']
    alarm_notifier.get_account_metadata = mock_get_account_metadata
    info = alarm_notifier.format_msg("test-alarm",test_iam_log)
    resp = alarm_notifier.send_sns(sns_arn, info)
    assert isinstance(resp, dict)

def test_get_account_metadata():
    # config = dotenv_values()
    # assert "TEST_ACCOUNT" in config.keys()
    # account_id = config['TEST_ACCOUNT']
    # (name,email)=alarm_notifier.get_account_metadata(account_id)
    # assert name=="tts-cloudgov-jump"
    pass

def test_get_cloudtrail_log_event():
    pass

def test_request_handler():
    pass
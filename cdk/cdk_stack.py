from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_secretsmanager as sm,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

class CdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        slack_secret_name = config.get("slack_secret_name") # type: str
        slack_secret = sm.Secret.from_secret_name_v2(self, "slack-secret", slack_secret_name)
        interval = str(config.get("interval"))
        log_group_name = config.get("log_group_name")
        alerts = config.get("alerts")
        sns_conf = config.get("sns")
        metric_namespace = config.get("namespace")

        # create sns topic and set subscribers
        sns_topic = sns.Topic(
            self,  
            id=sns_conf['name'],
            display_name=sns_conf['name'],
            topic_name=sns_conf['name']
        )
        for subscriber in sns_conf['subscribers']:
            sns_topic.add_subscription(subscriptions.EmailSubscription(subscriber))

        # add deps layer for lambda
        deps_layer = _lambda.LayerVersion(
            self,
            id="lambda-powertools",
            code=_lambda.Code.from_asset("./layers/deps-layer.zip")
        )

        # lambda to poll the health-api and post to slack
        cw_alarm_monitor = _lambda.Function(
            self,
            id='cloudwatch-alert-monitor',
            runtime=_lambda.Runtime.PYTHON_3_9,
            layers=[deps_layer],
            code=_lambda.Code.from_asset("./lambdas"),
            handler="alarm_notifier.handle_request",
            timeout= Duration.seconds(15),
            environment={
                "INTERVAL": interval,
                "SLACK_SECRET": slack_secret_name,
                "LOG_GROUP": log_group_name,
                "SNS_TOPIC_ARN": sns_topic.topic_arn,
                "NAMESPACE": metric_namespace
            }
        )

        # give lambda permission to make the api calls it needs
        api_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:FilterLogEvents", 
                "logs:DescribeMetricFilters" ,
                "organizations:ListAccounts",
                "sns:Publish"
            ],
            resources=['*']
        )
        cw_alarm_monitor.add_to_role_policy(api_policy)

        # give lambda permission to retrieve secret 
        secrets_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=[f"{slack_secret.secret_arn}*"]
        )
        cw_alarm_monitor.add_to_role_policy(secrets_policy)


        # create metric filter and alarms on our org log group
        org_log_group = logs.LogGroup.from_log_group_name(self, "org-log-group", log_group_name)
        
        # create the metrics and alarms
        alarm_names = list()
        for alert in alerts:
            mf=logs.MetricFilter(self, 
                id=f"{alert['name']}-Metric",
                log_group=org_log_group,
                filter_pattern=logs.FilterPattern.literal(alert['pattern']),
                metric_value=str(alert['threshold']),
                metric_name=alert['name'],
                default_value=0,
                metric_namespace=metric_namespace
            )
            metric = mf.metric().with_(statistic='sum')
            cloudwatch.Alarm(self,
                id=f"{alert['name']}-Alarm",
                alarm_name=alert['name'],
                alarm_description=alert['description'],
                metric=metric,
                threshold=alert['threshold'],
                evaluation_periods=1
            )
            alarm_names.append(alert['name'])

        # create filter pattern for Eventbridge Rule
        # catch cloudwatch alarm state change to "ALARM" on our Alarms
        alarm_pattern = events.EventPattern( 
            source=["aws.cloudwatch"],
            detail_type=["CloudWatch Alarm State Change"],
            detail={
                "alarmName" : alarm_names,
                "state": {
                    "value": ["ALARM"]
                }
            }
        )

        ## Create EventBridge Rule
        cw_alarm_events = events.Rule(
            self,
            "Notify-On-Alarms",
            description="Triggers Lambda to send notifications of CW Alarms trigger",
            event_pattern= alarm_pattern
        )
        ## add Lambda as target to rule
        cw_alarm_events.add_target(
            targets.LambdaFunction(cw_alarm_monitor)
        )
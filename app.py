#!/usr/bin/env python3
import os

import aws_cdk as cdk
import pprint
from cdk.cdk_stack import CdkStack

app = cdk.App()

context = app.node.try_get_context("environments")
config = context["default"]

CdkStack(app, "CloudTrail-Alerting-Stack", config)

app.synth()

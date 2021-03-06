from __future__ import print_function, absolute_import, division

import json
import logging
import subprocess
import time

from .configure_dns import normalize_domain

LOGGER = logging.getLogger("aws-certificate-management")
REGION = "--region=eu-west-1"


def run(command):
    # On clean build systems, the "aws ...." commands fail because no default
    # region is configured. We need to explicitly name it in every command.
    command.append(REGION)

    LOGGER.debug("Running this command: %r", command)
    subprocess.check_call(command)


def get_active_rule_set():
    """Return the name of the active rule set (if any), else None"""
    # Avoid throttling
    time.sleep(1)
    currently_active_rule_set = subprocess.check_output([
        'aws ses describe-active-receipt-rule-set ' + REGION],
        shell=True)
    if not currently_active_rule_set:
        return
    return json.loads(currently_active_rule_set)['Metadata']['Name']


def deactivate_rule_set_if_active(rule_set_name):
    if get_active_rule_set() != rule_set_name:
        return

    # Without parameter, set-active-receipt-rule-set deactivates the
    # currently active rule.
    run(['aws', 'ses', 'set-active-receipt-rule-set'])


def delete_rule_set(rule_set_name):
    """Delete the given rule set if it exists

    If the rule set is currently active (which would normally prevent
    deletion), the rule set is deactivated first.
    """
    deactivate_rule_set_if_active(rule_set_name)
    run(['aws', 'ses', 'delete-receipt-rule-set',
         '--rule-set-name', rule_set_name])


def generate_rule(domain, s3_bucket):
    rule = {
        "Name": "postmaster",
        "Enabled": True,
        "Recipients": ["postmaster@{0}".format(domain)],
        "Actions": [{
            "S3Action": {
                "BucketName": s3_bucket
            }
        }]
    }
    return json.dumps(rule)


def create_rule_set(rule_set_name, rule):
    """Create the given rule set and activate it

    This assumes that no rule set of that name currently exists
    """
    run(['aws', 'ses', 'create-receipt-rule-set',
         '--rule-set-name', rule_set_name])

    run(['aws', 'ses', 'create-receipt-rule',
         '--rule-set-name', rule_set_name, '--rule', rule])

    run(['aws', 'ses', 'set-active-receipt-rule-set',
         '--rule-set-name', rule_set_name])


def get_rule_set_name(domain):
    normalized_domain = normalize_domain(domain)
    return "standard_addresses_for_{0}".format(normalized_domain)


def setup_ses_rule_set(domain, s3_bucket):
    normalized_domain = normalize_domain(domain)
    rule = generate_rule(normalized_domain, s3_bucket)
    rule_set_name = get_rule_set_name(domain)

    delete_rule_set(rule_set_name)
    create_rule_set(rule_set_name, rule)


def cleanup_ses_rule_set(domain):
    rule_set_name = get_rule_set_name(domain)
    delete_rule_set(rule_set_name)
    LOGGER.info("Deletion of SES mail rule finished")
    LOGGER.warn("Check if you need to set an active rule in SES!")

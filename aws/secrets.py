import boto3
import json
from config import RDS_SECRET_ARN, AWS_REGION

_client = None


def _secrets_client():
    """One client for the process. Creating a boto3 client costs ~100ms, and this
    is now called on every new database connection, not just at startup."""
    global _client
    if _client is None:
        _client = boto3.session.Session().client('secretsmanager', region_name=AWS_REGION)
    return _client


def get_rds_credentials():
    """Fetch RDS username and password from AWS Secrets Manager.

    Always reads the live secret — never cached. The RDS-managed secret rotates on a
    schedule, so a cached password silently stops working mid-flight.
    """
    response = _secrets_client().get_secret_value(SecretId=RDS_SECRET_ARN)
    secret = json.loads(response['SecretString'])
    return secret['username'], secret['password']

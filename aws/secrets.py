import boto3
import json
import os
from config import AWS_REGION, RDS_SECRET_ARN

def get_db_secret():
    session = boto3.session.Session()
    client = session.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=RDS_SECRET_ARN)
    secret = json.loads(response['SecretString'])
    return secret
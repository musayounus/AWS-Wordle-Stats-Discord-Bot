import boto3
import json
from config import RDS_SECRET_ARN

def get_rds_credentials():
    session = boto3.session.Session()
    client = session.client('secretsmanager', region_name='eu-central-1')
    response = client.get_secret_value(SecretId=RDS_SECRET_ARN)
    secret = json.loads(response['SecretString'])
    return secret['username'], secret['password']
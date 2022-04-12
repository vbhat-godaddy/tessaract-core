import boto3
ssm = boto3.client('ssm')
env_val_dict = ssm.get_parameter(Name='/AdminParams/Team/Environment')
env_val = env_val_dict['Parameter']['Value']
team_val_dict = ssm.get_parameter(Name='/AdminParams/Team/Name')
team_val = team_val_dict['Parameter']['Value']

BASE_S3 = "s3://gd-" + team_val + "-" + env_val + "-tesseract"

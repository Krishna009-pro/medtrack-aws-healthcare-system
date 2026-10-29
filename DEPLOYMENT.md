# MedTrack Deployment Guide

## Prerequisites

- AWS Account with permission to provision EC2, IAM, DynamoDB, and SNS resources
- EC2 Instance (Amazon Linux 2023 or Ubuntu 22.04)
- Domain name (optional, for SSL)
- For local AWS setup, AWS CLI credentials. On EC2, attach an IAM instance profile instead; local AWS CLI credentials are not needed by the running app.

## Architecture Overview

```
Users → Nginx (80/443) → Gunicorn (8000) → Flask App → DynamoDB / SNS
```

## Quick Start (Local Development)

```bash
# Clone repository
git clone <repository-url>
cd medtrack-aws-healthcare-system

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Do not copy AWS keys into .env on EC2. Attach an IAM role to the instance.

# Run with Docker (includes local DynamoDB & SNS)
docker-compose up -d

# Or run directly in Local Mode
AWS_MODE=local python app.py
```

## AWS Infrastructure Setup

### Use the EC2 Instance Role for Runtime Credentials

Attach an IAM role through an EC2 instance profile. Boto3's standard credential provider chain retrieves and refreshes temporary credentials from EC2 instance metadata. The application does not need `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN` set when using this role. With `AWS_MODE=auto`, MedTrack checks that provider chain and selects AWS Mode when credentials are available.

Set the non-secret runtime configuration in the EC2 service environment (or export it in the shell for a direct launch):

```bash
export AWS_MODE=auto
export AWS_DEFAULT_REGION=us-east-1
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:ACCOUNT_ID:MedTrack-Alerts
export FLASK_ENV=production
export FLASK_DEBUG=False
export SECRET_KEY='replace-with-a-long-random-production-secret'

# Run once when the DynamoDB tables have not been created yet. The role
# currently attached to EC2 must have dynamodb:CreateTable for this step.
python scripts/init_dynamodb.py

# Launch the web app directly (default: http://<instance-public-ip>:5000)
python app.py
```

`AWS_REGION` takes precedence if both region variables are set. To route both notification categories to one SNS topic, set `SNS_TOPIC_ARN`; the two dedicated topic variables take precedence when present. The EC2 role needs `sns:Publish` on the configured topic ARN and the DynamoDB operations used by the application. Provision all six DynamoDB tables and their expected GSIs before app use; `python app.py` does not provision them. The `scripts/init_dynamodb.py` initializer creates missing tables but requires `dynamodb:CreateTable`. Either grant that action to the EC2 role temporarily while provisioning, or use an authorized provisioning role and run the initializer under its credentials before switching to a narrower runtime role. For this direct Flask run, permit inbound TCP port 5000 only from a trusted network source. The debug reloader is disabled when `FLASK_DEBUG=False`.

The direct Flask server started by `python app.py` is useful for a simple smoke run. For a public deployment, use the provided Gunicorn, systemd, and Nginx configuration.

### 1. Create IAM Role for EC2

```bash
# Create trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name MedTrack-EC2-Role \
  --assume-role-policy-document file://trust-policy.json
```

### 2. Attach Policies

The role used for first-time setup needs the runtime actions below, plus `dynamodb:CreateTable` and `dynamodb:UpdateTable` for GSIs. Its DynamoDB resources must include all six tables and their indexes. Replace the SNS ARN with the exact topic ARN(s); this sample uses a single SNS topic for both notification types.

```bash
# Create policy for DynamoDB access
cat > dynamodb-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:DescribeTable",
        "dynamodb:CreateTable",
        "dynamodb:UpdateTable"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/medtrack-*",
        "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/medtrack-*/index/*"
      ]
    }
  ]
}
EOF

# Create policy for SNS
cat > sns-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": [
        "arn:aws:sns:us-east-1:ACCOUNT_ID:MedTrack-Alerts"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name MedTrack-EC2-Role \
  --policy-name DynamoDBAccess \
  --policy-document file://dynamodb-policy.json

aws iam put-role-policy \
  --role-name MedTrack-EC2-Role \
  --policy-name SNSAccess \
  --policy-document file://sns-policy.json
```

After the six tables and GSIs are created, remove `dynamodb:CreateTable` and `dynamodb:UpdateTable` from the instance role policy. If you use two SNS topics, include both exact topic ARNs. IAM changes can take a short time to propagate.

### 3. Create Instance Profile

```bash
aws iam create-instance-profile --instance-profile-name MedTrack-Instance-Profile
aws iam add-role-to-instance-profile \
  --instance-profile-name MedTrack-Instance-Profile \
  --role-name MedTrack-EC2-Role
```

### 4. Launch EC2 Instance

```bash
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --subnet-id subnet-xxxxxxxx \
  --iam-instance-profile Name=MedTrack-Instance-Profile \
  --user-data file://user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=MedTrack-App}]'
```

### 5. User Data Script (user-data.sh)

```bash
#!/bin/bash
yum update -y
yum install -y python3 python3-pip nginx git

cd /home/ec2-user
git clone https://github.com/your-org/medtrack.git
cd medtrack

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p logs

cp nginx/medtrack.conf /etc/nginx/conf.d/medtrack.conf
nginx -t
systemctl restart nginx
systemctl enable nginx

cp systemd/medtrack.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable medtrack
systemctl start medtrack
```

## Database Setup

### Create DynamoDB Tables

```bash
# Use the EC2 instance role or another configured Boto3 credential provider.
# This initialization command requires dynamodb:CreateTable permissions.
python scripts/init_dynamodb.py
```

### Table Structure

| Table | Primary Key | GSIs |
|-------|-------------|------|
| medtrack-users | UserID | EmailIndex (Email) |
| medtrack-doctors | DoctorID | UserIDIndex (UserID) |
| medtrack-patients | PatientID | UserIDIndex (UserID) |
| medtrack-appointments | AppointmentID | PatientIDIndex, DoctorIDIndex |
| medtrack-diagnosis | DiagnosisID | AppointmentIDIndex, PatientIDIndex, DoctorIDIndex |
| medtrack-notifications | NotificationID | UserIDIndex |

## SNS Topics Setup

```bash
# Create appointment alerts topic
aws sns create-topic --name MedTrack-Appointment-Alerts

# Create diagnosis updates topic
aws sns create-topic --name MedTrack-Diagnosis-Updates

# Subscribe email/SMS endpoints
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789012:MedTrack-Appointment-Alerts \
  --protocol email \
  --notification-endpoint admin@example.com
```

## SSL/TLS with Let's Encrypt

```bash
# Install certbot
sudo yum install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal
sudo systemctl enable certbot-renew.timer
```

## Environment Variables

Set these values in the service environment or a protected configuration file. Do not store AWS access keys here; Boto3 uses the EC2 instance profile.

```bash
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-super-secret-key-min-32-chars

AWS_MODE=auto
AWS_DEFAULT_REGION=us-east-1
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:ACCOUNT_ID:MedTrack-Alerts
# AWS credentials are automatically loaded from the EC2 instance profile

DYNAMODB_USERS_TABLE=medtrack-users
DYNAMODB_DOCTORS_TABLE=medtrack-doctors
DYNAMODB_PATIENTS_TABLE=medtrack-patients
DYNAMODB_APPOINTMENTS_TABLE=medtrack-appointments
DYNAMODB_DIAGNOSIS_TABLE=medtrack-diagnosis
DYNAMODB_NOTIFICATIONS_TABLE=medtrack-notifications

# Or set separate SNS_APPOINTMENT_ALERTS_TOPIC and SNS_DIAGNOSIS_UPDATES_TOPIC values.

APP_URL=https://your-domain.com
```

## Monitoring

### CloudWatch Logs

```bash
# Install CloudWatch agent
sudo yum install -y amazon-cloudwatch-agent

# Configure
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
```

### CloudWatch Alarms

```bash
# CPU > 75%
aws cloudwatch put-metric-alarm \
  --alarm-name "MedTrack-High-CPU" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 75 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:MedTrack-Alerts

# 5xx errors
aws cloudwatch put-metric-alarm \
  --alarm-name "MedTrack-5xx-Errors" \
  --metric-name 5XXErrorRate \
  --namespace AWS/ApplicationELB \
  --statistic Average \
  --period 60 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

## Backup Strategy

```bash
# DynamoDB Point-in-Time Recovery (enable in console)
aws dynamodb update-continuous-backups \
  --table-name medtrack-users \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true

# Export to S3 (on-demand)
aws dynamodb export-table-to-point-in-time \
  --table-arn arn:aws:dynamodb:us-east-1:123456789012:table/medtrack-users \
  --s3-bucket your-backup-bucket \
  --s3-prefix medtrack-backups/users/
```

## Scaling

### Horizontal Scaling (ALB + Auto Scaling Group)

```bash
# Create Launch Template
aws ec2 create-launch-template \
  --launch-template-name MedTrack-Launch-Template \
  --version-description "Initial version" \
  --launch-template-data '{
    "ImageId": "ami-0c02fb55956c7d316",
    "InstanceType": "t3.medium",
    "IamInstanceProfile": {"Name": "MedTrack-Instance-Profile"},
    "UserData": "<base64-encoded-user-data>",
    "SecurityGroupIds": ["sg-xxxxxxxx"],
    "TagSpecifications": [{
      "ResourceType": "instance",
      "Tags": [{"Key": "Name", "Value": "MedTrack-App"}]
    }]
  }'

# Create Auto Scaling Group
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name MedTrack-ASG \
  --launch-template LaunchTemplateName=MedTrack-Launch-Template,Version='$Latest' \
  --min-size 2 \
  --max-size 10 \
  --desired-capacity 2 \
  --vpc-zone-identifier "subnet-xxx,subnet-yyy" \
  --target-group-arns arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/medtrack/xxxxxx
```

## Troubleshooting

### Check Application Logs

```bash
# Systemd logs
sudo journalctl -u medtrack -f

# Nginx logs
sudo tail -f /var/log/nginx/medtrack_access.log
sudo tail -f /var/log/nginx/medtrack_error.log

# Gunicorn logs
tail -f /home/ec2-user/medtrack/logs/gunicorn_access.log
tail -f /home/ec2-user/medtrack/logs/gunicorn_error.log
```

### Common Issues

1. **502 Bad Gateway**: Check if Gunicorn is running on port 8000
2. **DynamoDB Access Denied**: Verify IAM role attached to EC2
3. **SNS Notifications Not Sending**: Check topic ARN and permissions
4. **Static Files Not Loading**: Verify nginx static location config

## Security Checklist

- [ ] Use IAM Instance Profile (no hardcoded credentials)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Restrict security groups (only 80/443 from internet, 22 from admin IPs)
- [ ] Enable DynamoDB encryption at rest
- [ ] Enable VPC Flow Logs
- [ ] Set up AWS WAF for application protection
- [ ] Regular security updates: `yum update -y`
- [ ] Rotate secrets periodically

## Rollback Procedure

```bash
# If deployment fails, rollback to previous version
cd /home/ec2-user/medtrack
git checkout previous-release-tag
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart medtrack
```

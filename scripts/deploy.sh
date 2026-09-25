#!/bin/bash
# Deploy MedTrack to AWS EC2

set -e

APP_DIR="/home/ec2-user/medtrack"
REPO_URL="https://github.com/your-org/medtrack.git"
BRANCH="main"

echo "=== MedTrack Deployment Script ==="

# Update system
echo "Updating system packages..."
sudo yum update -y

# Install dependencies
echo "Installing dependencies..."
sudo yum install -y python3 python3-pip nginx git

# Create app directory
echo "Setting up application directory..."
mkdir -p $APP_DIR
cd $APP_DIR

# Clone or pull repository
if [ -d ".git" ]; then
    echo "Pulling latest changes..."
    git pull origin $BRANCH
else
    echo "Cloning repository..."
    git clone -b $BRANCH $REPO_URL .
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create logs directory
mkdir -p logs

# Run database initialization
echo "Initializing DynamoDB tables..."
python scripts/init_dynamodb.py

# Copy nginx configuration
echo "Configuring Nginx..."
sudo cp nginx/medtrack.conf /etc/nginx/conf.d/medtrack.conf
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# Copy systemd service
echo "Configuring systemd service..."
sudo cp systemd/medtrack.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable medtrack
sudo systemctl restart medtrack

# Check service status
echo "Checking service status..."
sudo systemctl status medtrack --no-pager

echo ""
echo "=== Deployment Complete ==="
echo "Application is running at http://your-domain.com"
echo "Check logs with: sudo journalctl -u medtrack -f"
#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Rating & Valuation Suite — build & push image to ECR
#
# Usage:
#   ./deploy/deploy.sh          # build linux/amd64 and push :latest to ECR
#
# There is NO always-on service anymore (the ECS Express service was deleted in
# July 2026 for cost reasons — it billed ~65 $/month for Fargate 24/7 + ALB +
# 3 public IPv4). The runtime model is now on-demand:
#
#   ./deploy/deploy.sh          # 1. push a new image (only after code changes)
#   ./deploy/start.sh           # 2. launch a Fargate SPOT task, prints the URL
#   ./deploy/stop.sh            # 3. stop it when done (auto-stops after 4h anyway)
#
# Fixed monthly cost: ECR storage only (~0.15 $/month, lifecycle policy keeps
# a single image). Runtime cost: ~0.02 $/hour on Fargate Spot.
#
# Prerequisites: AWS CLI configured, Docker running.
# -----------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="eu-west-1"
AWS_ACCOUNT="217267466515"
ECR_REPO="rating-valuation"
ECR_URI="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

echo "==> Authenticating to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Building image (linux/amd64)..."
docker build --platform linux/amd64 -t "${ECR_REPO}:latest" .

echo "==> Tagging..."
docker tag "${ECR_REPO}:latest" "${ECR_URI}:latest"

echo "==> Pushing to ECR..."
docker push "${ECR_URI}:latest"

echo ""
echo "==> Done. Launch the app with ./deploy/start.sh"

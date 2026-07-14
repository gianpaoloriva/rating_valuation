#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Rating & Valuation Suite — launch an on-demand Fargate SPOT task
#
# Usage:
#   ./deploy/start.sh                 # launch, wait, print http://<public-ip>:8501
#   ./deploy/start.sh --allow 1.2.3.4,5.6.7.0/24   # also admit these guest IPs
#   ./deploy/start.sh --open          # anyone with the link (like the old ALB)
#
# What it does:
#   1. restricts the security group ingress (port 8501) to YOUR current IP,
#      plus any --allow guests, or to the whole internet with --open
#   2. runs a single Fargate SPOT task (0.5 vCPU / 1 GB, ~0.02 $/hour)
#   3. waits for RUNNING and prints the public URL
#
# To admit a guest while the task is already running (no restart needed):
#   aws ec2 authorize-security-group-ingress --group-id sg-040737eb6164b6ec9 \
#     --protocol tcp --port 8501 --cidr <GUEST_IP>/32 --region eu-west-1
#
# The task self-terminates after 4 hours (timeout in the task definition), so a
# forgotten session can never cost more than a few cents. Stop it earlier with
# ./deploy/stop.sh. The public IP changes at every launch.
#
# Optional stable DNS name: export RV_HOSTED_ZONE_ID and RV_DNS_NAME before
# running and the script will upsert an A record in Route 53, e.g.
#   RV_HOSTED_ZONE_ID=Z123456 RV_DNS_NAME=rating.example.com ./deploy/start.sh
# -----------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="eu-west-1"
CLUSTER="default"
TASK_FAMILY="rating-valuation-ondemand"
SECURITY_GROUP="sg-040737eb6164b6ec9"   # rating-valuation-ondemand (default VPC)

OPEN=false
GUEST_CIDRS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --open) OPEN=true; shift ;;
    --allow)
      IFS=',' read -ra _CIDRS <<< "${2:?--allow requires a comma-separated IP list}"
      for c in "${_CIDRS[@]}"; do
        [[ "$c" == */* ]] || c="${c}/32"
        GUEST_CIDRS+=("$c")
      done
      shift 2 ;;
    *) echo "Unknown option: $1 (supported: --open, --allow ip1,ip2)"; exit 1 ;;
  esac
done

# --- 0. refuse to start a second task -----------------------------------------
RUNNING=$(aws ecs list-tasks --cluster "${CLUSTER}" --family "${TASK_FAMILY}" \
  --desired-status RUNNING --region "${AWS_REGION}" --query 'taskArns' --output text)
if [[ -n "${RUNNING}" && "${RUNNING}" != "None" ]]; then
  echo "A task is already running. Stop it first with ./deploy/stop.sh"
  exit 1
fi

# --- 1. set ingress: caller IP (+ guests) or open ------------------------------
if [[ "${OPEN}" == "true" ]]; then
  CIDRS=("0.0.0.0/0")
  echo "==> Opening port 8501 to the whole internet (--open)..."
else
  MY_IP=$(curl -s --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]')
  CIDRS=("${MY_IP}/32" "${GUEST_CIDRS[@]:-}")
  echo "==> Restricting port 8501 to: ${CIDRS[*]}"
fi
EXISTING=$(aws ec2 describe-security-groups --group-ids "${SECURITY_GROUP}" \
  --region "${AWS_REGION}" --query 'SecurityGroups[0].IpPermissions' --output json)
if [[ "${EXISTING}" != "[]" ]]; then
  aws ec2 revoke-security-group-ingress --group-id "${SECURITY_GROUP}" \
    --region "${AWS_REGION}" --ip-permissions "${EXISTING}" > /dev/null
fi
for CIDR in "${CIDRS[@]}"; do
  [[ -z "${CIDR}" ]] && continue
  aws ec2 authorize-security-group-ingress --group-id "${SECURITY_GROUP}" \
    --region "${AWS_REGION}" --protocol tcp --port 8501 --cidr "${CIDR}" > /dev/null
done

# --- 2. launch the task on Fargate SPOT ---------------------------------------
SUBNETS=$(aws ec2 describe-subnets --region "${AWS_REGION}" \
  --filters Name=default-for-az,Values=true \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')
echo "==> Launching Fargate SPOT task (${TASK_FAMILY})..."
TASK_ARN=$(aws ecs run-task \
  --cluster "${CLUSTER}" \
  --task-definition "${TASK_FAMILY}" \
  --capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1 \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=ENABLED}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].taskArn' --output text)
echo "    task: ${TASK_ARN##*/}"

# --- 3. wait for RUNNING and resolve the public IP ----------------------------
echo "==> Waiting for the task to be RUNNING (usually < 90s)..."
aws ecs wait tasks-running --cluster "${CLUSTER}" --tasks "${TASK_ARN}" --region "${AWS_REGION}"

ENI_ID=$(aws ecs describe-tasks --cluster "${CLUSTER}" --tasks "${TASK_ARN}" \
  --region "${AWS_REGION}" \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" --output text)
PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "${ENI_ID}" \
  --region "${AWS_REGION}" --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

# --- 4. optional stable DNS name via Route 53 ----------------------------------
URL="http://${PUBLIC_IP}:8501"
if [[ -n "${RV_HOSTED_ZONE_ID:-}" && -n "${RV_DNS_NAME:-}" ]]; then
  echo "==> Updating Route 53 record ${RV_DNS_NAME} -> ${PUBLIC_IP}..."
  aws route53 change-resource-record-sets --hosted-zone-id "${RV_HOSTED_ZONE_ID}" \
    --change-batch "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"${RV_DNS_NAME}\",\"Type\":\"A\",\"TTL\":60,\"ResourceRecords\":[{\"Value\":\"${PUBLIC_IP}\"}]}}]}" > /dev/null
  URL="http://${RV_DNS_NAME}:8501"
fi

echo ""
echo "==> App running (Streamlit may need ~30s more to boot):"
echo "    ${URL}"
echo "    Auto-stops in 4h; stop earlier with ./deploy/stop.sh"

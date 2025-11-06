#!/bin/bash
set -e

DOMAIN="awssolutionfinder.solutions.cloudnestle.com"
HOSTED_ZONE_NAME="cloudnestle.com"

echo "🌐 Setting up custom domain: ${DOMAIN}"
echo "=========================================="

# Get CloudFront distribution ID
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`UIUrl`].OutputValue' \
  --output text | sed 's|https://||' | sed 's|\.cloudfront\.net||')

if [ -z "$DIST_ID" ]; then
    echo "❌ CloudFront distribution not found"
    exit 1
fi

CLOUDFRONT_DOMAIN="${DIST_ID}.cloudfront.net"
echo "✅ CloudFront: ${CLOUDFRONT_DOMAIN}"

# Get Hosted Zone ID
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones \
  --query "HostedZones[?Name=='${HOSTED_ZONE_NAME}.'].Id" \
  --output text | cut -d'/' -f3)

if [ -z "$HOSTED_ZONE_ID" ]; then
    echo "❌ Hosted zone not found: ${HOSTED_ZONE_NAME}"
    exit 1
fi

echo "✅ Hosted Zone: ${HOSTED_ZONE_ID}"

# Create Route53 record
cat > /tmp/route53-change.json <<EOF
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "${DOMAIN}",
      "Type": "CNAME",
      "TTL": 300,
      "ResourceRecords": [{
        "Value": "${CLOUDFRONT_DOMAIN}"
      }]
    }
  }]
}
EOF

echo "📝 Creating Route53 record..."
aws route53 change-resource-record-sets \
  --hosted-zone-id ${HOSTED_ZONE_ID} \
  --change-batch file:///tmp/route53-change.json \
  --query 'ChangeInfo.Id' \
  --output text

echo ""
echo "✅ DNS record created!"
echo ""
echo "🌐 Your app will be available at:"
echo "   http://${DOMAIN}"
echo ""
echo "⏳ DNS propagation may take 5-10 minutes"
echo ""
echo "🔒 Note: For HTTPS, you need to:"
echo "   1. Request ACM certificate in us-east-1 for ${DOMAIN}"
echo "   2. Add certificate to CloudFront distribution"
echo "   3. Add alternate domain name to CloudFront"

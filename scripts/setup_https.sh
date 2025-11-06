#!/bin/bash
set -e

DOMAIN="awssolutionfinder.solutions.cloudnestle.com"
REGION="us-east-1"  # ACM for CloudFront must be in us-east-1

echo "🔒 Setting up HTTPS for ${DOMAIN}"
echo "=========================================="

# Get CloudFront distribution ID
CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name FaissRagStack \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`UIUrl`].OutputValue' \
  --output text | sed 's|https://||' | sed 's|/||')

DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?DomainName=='${CLOUDFRONT_DOMAIN}'].Id" \
  --output text)

echo "✅ CloudFront Distribution: ${DIST_ID}"

# Check if certificate already exists
CERT_ARN=$(aws acm list-certificates \
  --region ${REGION} \
  --query "CertificateSummaryList[?DomainName=='${DOMAIN}'].CertificateArn" \
  --output text)

if [ -z "$CERT_ARN" ]; then
    echo "📜 Requesting ACM certificate..."
    CERT_ARN=$(aws acm request-certificate \
      --domain-name ${DOMAIN} \
      --validation-method DNS \
      --region ${REGION} \
      --query 'CertificateArn' \
      --output text)
    
    echo "✅ Certificate requested: ${CERT_ARN}"
    echo ""
    echo "⏳ Waiting for validation records..."
    sleep 10
    
    # Get validation CNAME records
    VALIDATION=$(aws acm describe-certificate \
      --certificate-arn ${CERT_ARN} \
      --region ${REGION} \
      --query 'Certificate.DomainValidationOptions[0].ResourceRecord' \
      --output json)
    
    CNAME_NAME=$(echo $VALIDATION | jq -r '.Name')
    CNAME_VALUE=$(echo $VALIDATION | jq -r '.Value')
    
    echo "📝 Add this DNS record to validate certificate:"
    echo "   Type: CNAME"
    echo "   Name: ${CNAME_NAME}"
    echo "   Value: ${CNAME_VALUE}"
    echo ""
    echo "Run this command:"
    echo ""
    cat <<EOF
aws route53 change-resource-record-sets \\
  --hosted-zone-id Z092775411VSGE0TZPPML \\
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "${CNAME_NAME}",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "${CNAME_VALUE}"}]
      }
    }]
  }'
EOF
    echo ""
    echo "⏳ After adding the record, wait 5-10 minutes for validation"
    echo "   Then run: aws acm describe-certificate --certificate-arn ${CERT_ARN} --region ${REGION}"
    echo ""
    echo "Once validated, run this script again to update CloudFront"
    exit 0
else
    echo "✅ Certificate found: ${CERT_ARN}"
    
    # Check certificate status
    STATUS=$(aws acm describe-certificate \
      --certificate-arn ${CERT_ARN} \
      --region ${REGION} \
      --query 'Certificate.Status' \
      --output text)
    
    if [ "$STATUS" != "ISSUED" ]; then
        echo "⏳ Certificate status: ${STATUS}"
        echo "   Wait for certificate to be ISSUED before continuing"
        exit 1
    fi
    
    echo "✅ Certificate is ISSUED"
fi

# Get current CloudFront config
echo "📝 Updating CloudFront distribution..."
aws cloudfront get-distribution-config \
  --id ${DIST_ID} \
  --output json > /tmp/cf-config.json

ETAG=$(jq -r '.ETag' /tmp/cf-config.json)

# Update config with certificate and domain
jq --arg cert "$CERT_ARN" --arg domain "$DOMAIN" \
  '.DistributionConfig.Aliases.Quantity = 1 |
   .DistributionConfig.Aliases.Items = [$domain] |
   .DistributionConfig.ViewerCertificate = {
     "ACMCertificateArn": $cert,
     "SSLSupportMethod": "sni-only",
     "MinimumProtocolVersion": "TLSv1.2_2021",
     "Certificate": $cert,
     "CertificateSource": "acm"
   }' /tmp/cf-config.json | jq '.DistributionConfig' > /tmp/cf-config-updated.json

# Apply update
aws cloudfront update-distribution \
  --id ${DIST_ID} \
  --distribution-config file:///tmp/cf-config-updated.json \
  --if-match ${ETAG} \
  --query 'Distribution.Id' \
  --output text

echo ""
echo "✅ CloudFront updated!"
echo ""
echo "⏳ CloudFront deployment takes 5-15 minutes"
echo ""
echo "🌐 Your app will be available at:"
echo "   https://${DOMAIN}"

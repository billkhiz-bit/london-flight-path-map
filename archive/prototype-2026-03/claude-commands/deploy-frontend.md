Deploy the frontend to S3 and invalidate CloudFront cache.

Run these commands in sequence:
1. `AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2`
2. `AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"`

Report the invalidation ID when complete.

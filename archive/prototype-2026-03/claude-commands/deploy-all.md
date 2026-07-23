Deploy both frontend and backend.

First deploy the backend:
1. `cd backend && rm -rf .aws-sam && AWS_PROFILE=flightmap sam build && AWS_PROFILE=flightmap sam deploy`

Then deploy the frontend:
2. `AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2`
3. `AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"`

Report results for both deployments.

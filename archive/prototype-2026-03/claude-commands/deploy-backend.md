Deploy the backend Lambda functions via SAM.

Run these commands in sequence from the `backend/` directory:
1. `rm -rf .aws-sam`
2. `AWS_PROFILE=flightmap sam build`
3. `AWS_PROFILE=flightmap sam deploy`

Report the stack outputs when complete.

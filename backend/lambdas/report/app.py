import json

import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

REPORT_PROMPT = """Generate a comprehensive Property Intelligence Report for the following location. Write it as a professional advisory document that a property buyer would find genuinely useful.

Location: {location}
Borough/District: {borough}
Noise Level: {noise} (score {noise_score}/10 where 10 is noisiest)
Buyer Value Score: {score}/10
Nearest Airport: {airport} ({airport_dist} km)
Nearest Flight Path: {path_dist} km away
Average Property Price: {avg_price}
Annual Price Growth: {growth}
Crime Level: {crime} (rate: {crime_rate}/1,000 residents)
School Rating: {schools}
Transport Rating: {transport}
Flood Risk: {flood}
Air Quality: {air_quality}

Write the report with these exact section headers:

## EXECUTIVE SUMMARY
(3 sentences: overall verdict, key strength, key risk)

## NOISE ASSESSMENT
(Honest assessment of aircraft noise. Mention specific airports, flight paths, altitude estimates. Practical advice.)

## PROPERTY MARKET
(Current prices, growth trajectory, how it compares to London average. Buy/wait/negotiate advice.)

## LOCAL AMENITIES
(Schools, transport connections, healthcare. Be specific about tube lines, rail links, school names if you know them.)

## RISK FACTORS
(Crime, flood risk, air quality. Be honest but proportionate. Compare to London averages.)

## INVESTMENT OUTLOOK
(5-year perspective. Regeneration plans, transport improvements, demographic trends affecting value.)

## VERDICT
(Clear buy/consider/avoid recommendation with 3 bullet points of reasoning.)

Be specific and data-driven. Use the actual numbers provided. Keep each section 3-4 sentences. Do not pad with generic advice."""


def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        location_data = body.get('locationData', {})

        # Fill in defaults for missing fields
        defaults = {
            'location': 'Unknown',
            'borough': 'Unknown',
            'noise': 'Unknown',
            'noise_score': 'N/A',
            'score': 'N/A',
            'airport': 'Unknown',
            'airport_dist': 'N/A',
            'path_dist': 'N/A',
            'avg_price': 'N/A',
            'growth': 'N/A',
            'crime': 'Unknown',
            'crime_rate': 'N/A',
            'schools': 'Unknown',
            'transport': 'Unknown',
            'flood': 'Unknown',
            'air_quality': 'Unknown'
        }
        for k, v in defaults.items():
            location_data.setdefault(k, v)

        prompt = REPORT_PROMPT.format(**location_data)

        result = bedrock.invoke_model(
            modelId='us.amazon.nova-pro-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'system': [{'text': 'You are a senior property advisor at a London consultancy. Write formal, data-driven reports. Be direct and honest - buyers rely on your candour. Use British English.'}],
                'inferenceConfig': {
                    'maxTokens': 2048,
                    'temperature': 0.4,
                    'topP': 0.9
                }
            })
        )
        result_body = json.loads(result['body'].read())
        report = result_body['output']['message']['content'][0]['text']

        return response(200, {'report': report})

    except Exception:
        return response(500, {'error': 'Internal server error'})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(body)
    }

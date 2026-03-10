import json
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

SYSTEM_PROMPT = """You are a property analysis AI. Analyze property listing photos and provide insights relevant to a buyer.

Focus on:
- Property type (detached, semi-detached, terraced, flat, conversion, new-build, etc.)
- Approximate age/era of the building (Victorian, Edwardian, 1930s, post-war, modern)
- External condition (roof, walls, windows, guttering)
- Window type (single or double glazing - critical for aircraft noise insulation)
- Garden/outdoor space visible
- Parking availability
- Any visible issues (damp patches, cracks, leaning, subsidence signs)
- General kerb appeal and first impression

Be concise (3-5 sentences). Be honest about any concerns. If you cannot determine something, say so rather than guessing. If the image is not a property photo, say so briefly."""


def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        image_data = body.get('image', '')
        image_format = body.get('format', 'jpeg')
        analysis_type = body.get('type', 'listing')

        if not image_data:
            return response(400, {'error': 'Image data is required'})

        if analysis_type == 'listing':
            user_prompt = 'Analyze this property listing photo. What can you tell a potential buyer about this property from the image? Focus on condition, type, and any noise-insulation features like window glazing.'
        elif analysis_type == 'street':
            user_prompt = 'Analyze this street view. What can you tell about the neighbourhood? Comment on property types, street condition, parking, greenery, and general feel of the area.'
        else:
            user_prompt = 'Analyze this property-related image and provide relevant insights for a buyer.'

        messages = [{
            'role': 'user',
            'content': [
                {
                    'image': {
                        'format': image_format,
                        'source': {
                            'bytes': image_data
                        }
                    }
                },
                {'text': user_prompt}
            ]
        }]

        result = bedrock.invoke_model(
            modelId='us.amazon.nova-pro-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': messages,
                'system': [{'text': SYSTEM_PROMPT}],
                'inferenceConfig': {
                    'maxTokens': 512,
                    'temperature': 0.5,
                    'topP': 0.9
                }
            })
        )
        result_body = json.loads(result['body'].read())
        analysis = result_body['output']['message']['content'][0]['text']

        return response(200, {'analysis': analysis})

    except Exception as e:
        return response(500, {'error': str(e)})


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

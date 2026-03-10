import json
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

EPC_PROMPT = """Analyze this Energy Performance Certificate (EPC). Extract and interpret the following:

1. EPC Band (A-G) and numerical score
2. Current energy efficiency rating
3. Potential energy efficiency rating
4. Key recommendations for improvement
5. Estimated energy costs
6. Environmental impact rating
7. Wall, roof, and window insulation details (critical for noise)

Provide a buyer-focused summary in 4-5 sentences. Highlight:
- Whether the glazing is single, double, or triple (important for aircraft noise areas)
- The most cost-effective improvements
- Whether the rating is typical for the property age
- Any red flags

Format the key data as a brief structured summary followed by your interpretation."""

SURVEY_PROMPT = """Analyze this property survey report. Extract and summarize the key findings for a buyer:

1. Overall condition rating
2. Structural issues identified (subsidence, movement, cracks)
3. Roof condition
4. Damp issues (rising damp, penetrating damp, condensation)
5. Window and door condition (important for noise insulation)
6. Electrical and plumbing condition
7. External areas and drainage
8. Any urgent repairs needed
9. Estimated repair costs if mentioned

Provide a buyer-focused summary in 5-6 sentences. Highlight:
- Critical issues that could affect the purchase decision
- Estimated cost implications
- Whether issues are typical for the property age
- Negotiation points based on the findings

IMPORTANT: This is an AI summary. Always recommend the buyer reads the full report and consults their surveyor for clarification."""


def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        doc_data = body.get('document', '')
        doc_format = body.get('format', 'jpeg')
        doc_type = body.get('type', 'epc')

        if not doc_data:
            return response(400, {'error': 'Document data is required'})

        prompt = EPC_PROMPT if doc_type == 'epc' else SURVEY_PROMPT

        # Build content based on format
        if doc_format == 'pdf':
            content_block = {
                'document': {
                    'format': 'pdf',
                    'name': 'uploaded_document',
                    'source': {
                        'bytes': doc_data
                    }
                }
            }
        else:
            content_block = {
                'image': {
                    'format': doc_format,
                    'source': {
                        'bytes': doc_data
                    }
                }
            }

        messages = [{
            'role': 'user',
            'content': [
                content_block,
                {'text': prompt}
            ]
        }]

        system_text = 'You are a property document analysis AI helping UK home buyers understand technical documents. Be accurate, concise, and buyer-focused. Always note that this is an AI interpretation and the buyer should consult professionals.'

        result = bedrock.invoke_model(
            modelId='us.amazon.nova-pro-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': messages,
                'system': [{'text': system_text}],
                'inferenceConfig': {
                    'maxTokens': 1024,
                    'temperature': 0.3,
                    'topP': 0.9
                }
            })
        )
        result_body = json.loads(result['body'].read())
        analysis = result_body['output']['message']['content'][0]['text']

        return response(200, {
            'analysis': analysis,
            'type': doc_type,
            'disclaimer': 'AI-generated summary. Always read the full document and consult qualified professionals before making property decisions.'
        })

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

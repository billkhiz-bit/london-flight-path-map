import json
import boto3

# Use us-east-1 where Amazon Nova models are available
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

BOROUGH_DATA = {
    "Hounslow": {"noise":"severe","price":"£430K","growth":"4.2%","crime":"medium","crimeRate":89,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Piccadilly line, direct Heathrow access"},
    "Hillingdon": {"noise":"severe","price":"£450K","growth":"3.8%","crime":"medium","crimeRate":82,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Elizabeth line, Metropolitan line, Heathrow"},
    "Richmond": {"noise":"moderate","price":"£850K","growth":"3.5%","crime":"low","crimeRate":58,"schools":"excellent","flood":"medium","airQuality":"good","transport":"good","transportNote":"District line, Overground, river links"},
    "Wandsworth": {"noise":"moderate","price":"£680K","growth":"4.0%","crime":"medium","crimeRate":78,"schools":"excellent","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Northern line, Overground, Battersea extension"},
    "Kingston": {"noise":"low","price":"£530K","growth":"3.9%","crime":"low","crimeRate":62,"schools":"excellent","flood":"medium","airQuality":"good","transport":"moderate","transportNote":"South Western Railway, no tube"},
    "Ealing": {"noise":"high","price":"£520K","growth":"4.5%","crime":"medium","crimeRate":85,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Elizabeth line, Central line, District line"},
    "Hammersmith": {"noise":"moderate","price":"£720K","growth":"3.2%","crime":"medium","crimeRate":91,"schools":"good","flood":"medium","airQuality":"moderate","transport":"excellent","transportNote":"6 tube lines, major interchange hub"},
    "Lambeth": {"noise":"moderate","price":"£550K","growth":"4.8%","crime":"high","crimeRate":105,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Victoria, Northern, Bakerloo, Overground"},
    "Southwark": {"noise":"moderate","price":"£560K","growth":"4.5%","crime":"high","crimeRate":108,"schools":"good","flood":"medium","airQuality":"moderate","transport":"excellent","transportNote":"Jubilee, Northern, Bakerloo, Overground"},
    "Greenwich": {"noise":"moderate-high","price":"£420K","growth":"5.2%","crime":"medium","crimeRate":88,"schools":"good","flood":"high","airQuality":"moderate","transport":"good","transportNote":"Elizabeth line, Jubilee, DLR, Thames Clipper"},
    "Lewisham": {"noise":"low","price":"£430K","growth":"5.5%","crime":"medium","crimeRate":86,"schools":"good","flood":"low","airQuality":"good","transport":"good","transportNote":"DLR, Overground, Bakerloo extension planned"},
    "Tower Hamlets": {"noise":"moderate","price":"£480K","growth":"3.8%","crime":"high","crimeRate":115,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Central, District, Hammersmith, DLR, Elizabeth line"},
    "Newham": {"noise":"high","price":"£380K","growth":"5.8%","crime":"high","crimeRate":102,"schools":"improving","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Elizabeth line, Jubilee, DLR, London City Airport"},
    "Bexley": {"noise":"moderate","price":"£370K","growth":"4.5%","crime":"low","crimeRate":61,"schools":"good","flood":"medium","airQuality":"good","transport":"moderate","transportNote":"Elizabeth line (Abbey Wood), limited tube"},
    "Bromley": {"noise":"low","price":"£480K","growth":"3.5%","crime":"low","crimeRate":59,"schools":"excellent","flood":"low","airQuality":"good","transport":"moderate","transportNote":"National Rail, no tube, Bromley South fast to Victoria"},
    "Croydon": {"noise":"low-moderate","price":"£360K","growth":"5.0%","crime":"high","crimeRate":95,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Tram network, East Croydon fast trains, Overground"},
    "Sutton": {"noise":"low","price":"£400K","growth":"3.8%","crime":"low","crimeRate":56,"schools":"excellent","flood":"low","airQuality":"good","transport":"moderate","transportNote":"National Rail, tram extension planned"},
    "Merton": {"noise":"low","price":"£550K","growth":"3.6%","crime":"low","crimeRate":64,"schools":"good","flood":"low","airQuality":"good","transport":"good","transportNote":"District line, Northern line, tram"},
    "Westminster": {"noise":"moderate","price":"£1,100K","growth":"2.5%","crime":"high","crimeRate":180,"schools":"good","flood":"low","airQuality":"poor","transport":"excellent","transportNote":"Major hub, most tube lines, Crossrail"},
    "Camden": {"noise":"low","price":"£780K","growth":"3.0%","crime":"high","crimeRate":120,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Northern, Victoria, Metropolitan, Overground"},
    "Islington": {"noise":"low","price":"£650K","growth":"3.2%","crime":"high","crimeRate":118,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Victoria, Northern, Piccadilly, Overground"},
    "Hackney": {"noise":"low","price":"£550K","growth":"4.5%","crime":"high","crimeRate":110,"schools":"improving","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Overground, future Crossrail 2"},
    "Haringey": {"noise":"low","price":"£520K","growth":"4.2%","crime":"medium","crimeRate":88,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Victoria, Piccadilly, Overground"},
    "Enfield": {"noise":"low","price":"£400K","growth":"4.8%","crime":"medium","crimeRate":76,"schools":"good","flood":"low","airQuality":"good","transport":"moderate","transportNote":"Piccadilly line, Overground, National Rail"},
    "Waltham Forest": {"noise":"low","price":"£450K","growth":"5.2%","crime":"medium","crimeRate":82,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Victoria line, Overground"},
    "Redbridge": {"noise":"low","price":"£440K","growth":"4.5%","crime":"medium","crimeRate":78,"schools":"excellent","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Central line, Elizabeth line"},
    "Barking": {"noise":"moderate","price":"£320K","growth":"6.0%","crime":"high","crimeRate":98,"schools":"improving","flood":"high","airQuality":"poor","transport":"good","transportNote":"District line, Hammersmith line, Overground, C2C"},
    "Havering": {"noise":"low","price":"£380K","growth":"4.0%","crime":"low","crimeRate":65,"schools":"good","flood":"medium","airQuality":"good","transport":"moderate","transportNote":"Elizabeth line, District line, C2C"},
    "Barnet": {"noise":"low","price":"£560K","growth":"3.5%","crime":"medium","crimeRate":72,"schools":"excellent","flood":"low","airQuality":"good","transport":"good","transportNote":"Northern line, Thameslink"}
}

SYSTEM_PROMPT = f"""You are an AI property advisor for London. You help property buyers assess areas based on real data.

You have access to data for 29 London boroughs covering: noise impact, average property prices, price growth, crime rates, school ratings, flood risk, air quality, and transport links.

Borough data:
{json.dumps(BOROUGH_DATA, indent=2)}

Guidelines:
- Be specific: quote actual prices, crime rates, transport lines
- Be honest about trade-offs (e.g. "quieter but longer commute")
- When asked to recommend areas, suggest 2-3 options with reasoning
- Mention the Buyer Value Score factors: Quiet Skies (40%), Affordability (35%), Growth (25%)
- Always remind users this is guidance, not professional property advice
- Keep responses concise (2-3 paragraphs max)
- If asked about a specific postcode, relate it to the nearest borough data
"""


def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        message = body.get('message', '')

        if not message:
            return response(400, {'error': 'Message is required'})

        result = bedrock.invoke_model(
            modelId='us.amazon.nova-2-lite-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': message}]}],
                'system': [{'text': SYSTEM_PROMPT}],
                'inferenceConfig': {
                    'maxTokens': 1024,
                    'temperature': 0.7,
                    'topP': 0.9
                }
            })
        )

        result_body = json.loads(result['body'].read())
        reply = result_body['output']['message']['content'][0]['text']

        return response(200, {'reply': reply})

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

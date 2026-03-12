import concurrent.futures
import json

import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

BOROUGH_DATA = {
    # London boroughs (synced from frontend BOROUGH_DATA_RAW + BOROUGH_EXTRA)
    "Hounslow": {"noise":"severe","price":"£465K","growth":"3.2%","crime":"medium","crimeRate":89,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Hillingdon": {"noise":"severe","price":"£480K","growth":"2.8%","crime":"low","crimeRate":72,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Richmond upon Thames": {"noise":"high","price":"£825K","growth":"1.5%","crime":"low","crimeRate":58,"schools":"excellent","flood":"medium","airQuality":"good","transport":"good"},
    "Ealing": {"noise":"high","price":"£540K","growth":"4.1%","crime":"medium","crimeRate":88,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent"},
    "Wandsworth": {"noise":"moderate","price":"£680K","growth":"2.1%","crime":"medium","crimeRate":82,"schools":"excellent","flood":"medium","airQuality":"moderate","transport":"excellent"},
    "Lambeth": {"noise":"moderate","price":"£560K","growth":"3.5%","crime":"high","crimeRate":115,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent"},
    "Lewisham": {"noise":"low-moderate","price":"£445K","growth":"4.8%","crime":"medium","crimeRate":91,"schools":"good","flood":"medium","airQuality":"moderate","transport":"good"},
    "Greenwich": {"noise":"moderate","price":"£430K","growth":"5.2%","crime":"medium","crimeRate":93,"schools":"good","flood":"high","airQuality":"moderate","transport":"good"},
    "Tower Hamlets": {"noise":"low-moderate","price":"£495K","growth":"2.0%","crime":"high","crimeRate":120,"schools":"good","flood":"high","airQuality":"poor","transport":"excellent"},
    "Camden": {"noise":"low","price":"£780K","growth":"1.2%","crime":"high","crimeRate":130,"schools":"excellent","flood":"low","airQuality":"poor","transport":"excellent"},
    "Islington": {"noise":"low","price":"£720K","growth":"1.8%","crime":"high","crimeRate":125,"schools":"good","flood":"low","airQuality":"poor","transport":"excellent"},
    "Hackney": {"noise":"low","price":"£590K","growth":"3.0%","crime":"high","crimeRate":112,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent"},
    "Barnet": {"noise":"low-moderate","price":"£560K","growth":"3.1%","crime":"low","crimeRate":74,"schools":"excellent","flood":"low","airQuality":"good","transport":"good"},
    "Croydon": {"noise":"moderate","price":"£395K","growth":"4.5%","crime":"medium","crimeRate":98,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Bromley": {"noise":"low","price":"£480K","growth":"3.8%","crime":"low","crimeRate":65,"schools":"excellent","flood":"low","airQuality":"good","transport":"moderate"},
    "Newham": {"noise":"moderate-high","price":"£410K","growth":"5.8%","crime":"high","crimeRate":108,"schools":"good","flood":"high","airQuality":"poor","transport":"excellent"},
    "Southwark": {"noise":"low-moderate","price":"£530K","growth":"2.5%","crime":"high","crimeRate":118,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent"},
    "Hammersmith and Fulham": {"noise":"moderate-high","price":"£750K","growth":"1.0%","crime":"medium","crimeRate":96,"schools":"excellent","flood":"high","airQuality":"moderate","transport":"excellent"},
    "Kensington and Chelsea": {"noise":"moderate","price":"£1,350K","growth":"0.5%","crime":"medium","crimeRate":95,"schools":"excellent","flood":"medium","airQuality":"moderate","transport":"excellent"},
    "Brent": {"noise":"low-moderate","price":"£490K","growth":"4.0%","crime":"medium","crimeRate":92,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Haringey": {"noise":"low","price":"£545K","growth":"3.5%","crime":"medium","crimeRate":99,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Waltham Forest": {"noise":"low","price":"£480K","growth":"4.2%","crime":"medium","crimeRate":88,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Merton": {"noise":"low-moderate","price":"£560K","growth":"2.8%","crime":"low","crimeRate":70,"schools":"good","flood":"low","airQuality":"moderate","transport":"good"},
    "Redbridge": {"noise":"low","price":"£445K","growth":"3.9%","crime":"medium","crimeRate":83,"schools":"excellent","flood":"low","airQuality":"moderate","transport":"good"},
    "Enfield": {"noise":"low","price":"£430K","growth":"4.3%","crime":"medium","crimeRate":85,"schools":"good","flood":"low","airQuality":"good","transport":"moderate"},
    "Kingston upon Thames": {"noise":"low-moderate","price":"£550K","growth":"2.0%","crime":"low","crimeRate":62,"schools":"excellent","flood":"medium","airQuality":"good","transport":"good"},
    "Sutton": {"noise":"low","price":"£415K","growth":"3.5%","crime":"low","crimeRate":60,"schools":"excellent","flood":"low","airQuality":"good","transport":"moderate"},
    "Westminster": {"noise":"moderate","price":"£980K","growth":"0.8%","crime":"high","crimeRate":175,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent"},
    "City of London": {"noise":"low-moderate","price":"£850K","growth":"1.0%","crime":"high","crimeRate":190,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent"},
    "Barking": {"noise":"low","price":"£340K","growth":"5.8%","crime":"high","crimeRate":105,"schools":"good","flood":"medium","airQuality":"moderate","transport":"good"},
    "Havering": {"noise":"low","price":"£400K","growth":"4.0%","crime":"low","crimeRate":72,"schools":"good","flood":"low","airQuality":"good","transport":"moderate"},
    "Bexley": {"noise":"low","price":"£380K","growth":"4.5%","crime":"low","crimeRate":68,"schools":"good","flood":"medium","airQuality":"good","transport":"moderate"},
    "Harrow": {"noise":"low","price":"£490K","growth":"3.2%","crime":"low","crimeRate":70,"schools":"excellent","flood":"low","airQuality":"good","transport":"good"},
    # NYC boroughs (synced from frontend NYC_BOROUGH_DATA_RAW + NYC_BOROUGH_EXTRA)
    "Queens": {"noise":"severe","price":"$620K","growth":"4.5%","crime":"medium","crimeRate":78,"schools":"good","flood":"high","airQuality":"moderate","transport":"excellent"},
    "Brooklyn": {"noise":"high","price":"$850K","growth":"3.8%","crime":"medium","crimeRate":82,"schools":"good","flood":"medium","airQuality":"moderate","transport":"excellent"},
    "Manhattan": {"noise":"moderate","price":"$1,200K","growth":"2.0%","crime":"medium","crimeRate":95,"schools":"excellent","flood":"medium","airQuality":"poor","transport":"excellent"},
    "Bronx": {"noise":"low-moderate","price":"$420K","growth":"5.5%","crime":"high","crimeRate":110,"schools":"good","flood":"low","airQuality":"poor","transport":"good"},
    "Staten Island": {"noise":"low","price":"$550K","growth":"3.0%","crime":"low","crimeRate":52,"schools":"good","flood":"high","airQuality":"good","transport":"poor"},
}

# --- Agent System Prompts ---

ORCHESTRATOR_PROMPT = """You are the orchestrator for Sky Score, a multi-agent property intelligence system. Your job is to analyse the user's query and determine which specialist agents to invoke.

Available agents:
1. NOISE_ANALYST - aircraft noise, flight paths, airport proximity, sound insulation, glazing advice
2. PROPERTY_RESEARCHER - prices, affordability, investment potential, growth trends, rental yields
3. NEIGHBOURHOOD_SCORER - schools, crime, transport, healthcare, livability, amenities

Rules:
- For simple single-topic questions, invoke only the relevant agent (1 agent)
- For comparisons or multi-criteria questions, invoke all relevant agents (2-3 agents)
- For broad "should I buy" or "tell me about" questions, invoke all 3 agents

Respond ONLY with a JSON object in this exact format, nothing else:
{"agents": ["NOISE_ANALYST", "PROPERTY_RESEARCHER", "NEIGHBOURHOOD_SCORER"], "areas": ["Hounslow", "Richmond"], "summary": "comparing two areas for family buyer"}

Only include agents that are needed. The "areas" field should list the specific boroughs or neighbourhoods mentioned. The "summary" field should be a brief description of the query intent."""

NOISE_AGENT_PROMPT = """You are the Noise Analyst agent for Sky Score. You specialise in aircraft noise assessment for property buyers.

Borough data:
{borough_data}

Your analysis must cover:
- Aircraft noise level for each area mentioned
- Proximity to airports and flight paths
- Impact on daily life (morning/evening, garden use, sleep)
- Sound insulation recommendations (glazing type, estimated cost)
- How noise compares between areas if multiple are mentioned

Be specific with data. Keep your analysis to 3-5 sentences. Format as plain text, not bullet points."""

PROPERTY_AGENT_PROMPT = """You are the Property Researcher agent for Sky Score. You specialise in market analysis and investment potential.

Borough data:
{borough_data}

Your analysis must cover:
- Current average prices for areas mentioned
- Price growth trends and trajectory
- Affordability assessment relative to budget if mentioned
- Investment potential (yield estimates, regeneration plans)
- Value comparison between areas if multiple are mentioned

Be specific with data. Keep your analysis to 3-5 sentences. Format as plain text, not bullet points."""

NEIGHBOURHOOD_AGENT_PROMPT = """You are the Neighbourhood Scorer agent for Sky Score. You specialise in livability assessment for property buyers.

Borough data:
{borough_data}

Your analysis must cover:
- School quality ratings for areas mentioned
- Crime rates and safety assessment
- Transport connectivity (tube lines, rail, commute times)
- Healthcare access and local amenities
- Overall livability comparison if multiple areas mentioned

Be specific with data. Keep your analysis to 3-5 sentences. Format as plain text, not bullet points."""

SYNTHESISER_PROMPT = """You are the Synthesiser for Sky Score's multi-agent system. You receive analysis from specialist agents and combine them into a single, coherent recommendation for the property buyer.

You will receive outputs from these agents:
- NOISE_ANALYST: aircraft noise assessment
- PROPERTY_RESEARCHER: market and investment analysis
- NEIGHBOURHOOD_SCORER: livability and amenities assessment

Your job:
1. Combine all agent findings into a unified, natural response
2. Highlight key trade-offs between areas if comparing
3. Give a clear recommendation with reasoning
4. Mention which factors favour which areas
5. Keep the response concise (3-4 paragraphs max)
6. CRITICAL: Never contradict noise data. If an agent reports severe/high noise for an area, your recommendation must reflect that - never describe that area as quiet or having peaceful skies. Your verdict must be consistent with the noise assessment.

Do not mention the agents by name. Write as if you are a single knowledgeable property advisor delivering a complete assessment. Be direct and actionable."""


def call_nova_lite(system_prompt, user_message, max_tokens=512):
    """Call Nova Lite for fast agent responses."""
    result = bedrock.invoke_model(
        modelId='us.amazon.nova-2-lite-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'messages': [{'role': 'user', 'content': [{'text': user_message}]}],
            'system': [{'text': system_prompt}],
            'inferenceConfig': {'maxTokens': max_tokens, 'temperature': 0.3, 'topP': 0.9}
        })
    )
    body = json.loads(result['body'].read())
    return body['output']['message']['content'][0]['text']


def call_nova_pro(system_prompt, user_message, max_tokens=1536):
    """Call Nova Pro for synthesis and deep reasoning."""
    result = bedrock.invoke_model(
        modelId='us.amazon.nova-pro-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'messages': [{'role': 'user', 'content': [{'text': user_message}]}],
            'system': [{'text': system_prompt}],
            'inferenceConfig': {'maxTokens': max_tokens, 'temperature': 0.5, 'topP': 0.9}
        })
    )
    body = json.loads(result['body'].read())
    return body['output']['message']['content'][0]['text']


def run_agent(agent_name, query, borough_data_str):
    """Run a single specialist agent."""
    prompts = {
        'NOISE_ANALYST': NOISE_AGENT_PROMPT,
        'PROPERTY_RESEARCHER': PROPERTY_AGENT_PROMPT,
        'NEIGHBOURHOOD_SCORER': NEIGHBOURHOOD_AGENT_PROMPT,
    }
    system = prompts[agent_name].format(borough_data=borough_data_str)
    return {'agent': agent_name, 'analysis': call_nova_lite(system, query)}


def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        query = body.get('message', '')
        viewing_context = body.get('context', '')

        if not query:
            return api_response(400, {'error': 'Message is required'})

        user_message = query
        if viewing_context:
            user_message = f"[User is viewing: {viewing_context}]\n\n{query}"

        borough_data_str = json.dumps(BOROUGH_DATA, indent=1)

        # Step 1: Orchestrator determines which agents to invoke
        orchestrator_reply = call_nova_lite(ORCHESTRATOR_PROMPT, user_message, max_tokens=256)

        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = orchestrator_reply
            if '```' in json_str:
                json_str = json_str.split('```')[1]
                if json_str.startswith('json'):
                    json_str = json_str[4:]
            json_str = json_str.strip()
            plan = json.loads(json_str)
            agents_to_run = plan.get('agents', ['NOISE_ANALYST', 'PROPERTY_RESEARCHER', 'NEIGHBOURHOOD_SCORER'])
            areas = plan.get('areas', [])
            plan_summary = plan.get('summary', '')
        except (json.JSONDecodeError, IndexError):
            # Fallback: run all agents
            agents_to_run = ['NOISE_ANALYST', 'PROPERTY_RESEARCHER', 'NEIGHBOURHOOD_SCORER']
            areas = []
            plan_summary = 'full analysis'

        # Validate agent names
        valid_agents = {'NOISE_ANALYST', 'PROPERTY_RESEARCHER', 'NEIGHBOURHOOD_SCORER'}
        agents_to_run = [a for a in agents_to_run if a in valid_agents]
        if not agents_to_run:
            agents_to_run = list(valid_agents)

        # Step 2: Run specialist agents in parallel
        agent_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(run_agent, agent, user_message, borough_data_str): agent
                for agent in agents_to_run
            }
            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result()
                    agent_results[result['agent']] = result['analysis']
                except Exception as agent_err:
                    agent_results[agent_name] = f"Analysis unavailable: agent encountered an error"

        # Step 3: Synthesise all agent outputs with Nova Pro
        synthesis_input = f"User query: {user_message}\n\n"
        for agent_name, analysis in agent_results.items():
            label = {
                'NOISE_ANALYST': 'Noise Analysis',
                'PROPERTY_RESEARCHER': 'Property Market Analysis',
                'NEIGHBOURHOOD_SCORER': 'Neighbourhood Assessment'
            }.get(agent_name, agent_name)
            synthesis_input += f"--- {label} ---\n{analysis}\n\n"

        final_reply = call_nova_pro(SYNTHESISER_PROMPT, synthesis_input)

        return api_response(200, {
            'reply': final_reply,
            'model': 'multi-agent',
            'agents_used': list(agent_results.keys()),
            'agent_outputs': agent_results,
            'plan': {
                'agents': agents_to_run,
                'areas': areas,
                'summary': plan_summary
            }
        })

    except Exception as e:
        return api_response(500, {'error': str(e)})


def api_response(status, body):
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

def get_user_from_session(session_token: str):
    """Get user info from marketplace session token."""
    global dynamodb
    
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    
    # Marketplace session table
    session_table = dynamodb.Table('MP-1759859484941-DataStackSessionTable8346BE43-1D25U1YXAV1JW')
    user_table = dynamodb.Table('MP-1759859484941-DataStackUserTableDAF10CB8-MM0KVOMUI09Z')
    
    try:
        # Get session info
        session_response = session_table.get_item(
            Key={'sessionId': session_token}
        )
        
        if 'Item' not in session_response:
            return None
            
        session = session_response['Item']
        
        # Check if session is expired
        expires_at = session.get('expiresAt')
        if expires_at and datetime.now().timestamp() > expires_at:
            return None
            
        user_id = session.get('userId')
        if not user_id:
            return None
            
        # Get user info
        user_response = user_table.get_item(
            Key={'userId': user_id}
        )
        
        if 'Item' not in user_response:
            return None
            
        user = user_response['Item']
        return {
            'user_id': user['userId'],
            'email': user.get('email', 'unknown'),
            'tier': 'free',  # Marketplace users get free tier (10 searches/day)
            'role': user.get('role', 'customer')
        }
        
    except Exception as e:
        print(f"Error looking up session: {e}")
        return None

def get_user_from_email(email: str):
    """Get user info from marketplace by email."""
    global dynamodb
    
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    
    # Marketplace user table
    user_table = dynamodb.Table('MP-1759859484941-DataStackUserTableDAF10CB8-MM0KVOMUI09Z')
    
    try:
        # Use EmailIndex GSI to find user by email
        response = user_table.query(
            IndexName='EmailIndex',
            KeyConditionExpression='email = :email',
            ExpressionAttributeValues={':email': email}
        )
        
        if response['Items']:
            user = response['Items'][0]
            return {
                'user_id': user['userId'],
                'email': user.get('email', 'unknown'),
                'tier': 'free',  # Marketplace users get free tier (10 searches/day)
                'role': user.get('role', 'customer')
            }
        return None
        
    except Exception as e:
        print(f"Error looking up user by email: {e}")
        return None

def get_user_id(event):
    """Generate user ID from various authentication methods."""
    # Check for marketplace parameter
    is_marketplace = False
    
    # Check query parameters for marketplace flag
    if 'queryStringParameters' in event and event['queryStringParameters']:
        is_marketplace = event['queryStringParameters'].get('marketplace') == 'true'
    
    # Check body for marketplace flag
    if not is_marketplace:
        try:
            if 'body' in event:
                body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
                is_marketplace = body.get('marketplace') == 'true'
        except:
            pass
    
    # If marketplace=true, try to authenticate via session or email
    if is_marketplace:
        # Try session token from headers
        session_token = None
        if 'headers' in event:
            # Check for session in Authorization header
            auth_header = event['headers'].get('Authorization', '')
            if auth_header.startswith('Bearer '):
                session_token = auth_header.replace('Bearer ', '')
            
            # Check for session cookie
            cookie_header = event['headers'].get('Cookie', '')
            if 'marketplace_session=' in cookie_header:
                for cookie in cookie_header.split(';'):
                    if cookie.strip().startswith('marketplace_session='):
                        session_token = cookie.split('=')[1].strip()
                        break
        
        # Try session authentication
        if session_token:
            user_info = get_user_from_session(session_token)
            if user_info:
                return user_info['user_id'], user_info['tier'], user_info
        
        # Try email from query parameters (for testing)
        email = None
        if 'queryStringParameters' in event and event['queryStringParameters']:
            email = event['queryStringParameters'].get('email')
        
        if email:
            user_info = get_user_from_email(email)
            if user_info:
                return user_info['user_id'], user_info['tier'], user_info
    
    # Check for API key (existing logic)
    api_key = None
    
    # Try query parameters first
    if 'queryStringParameters' in event and event['queryStringParameters']:
        api_key = event['queryStringParameters'].get('apikey')
    
    # Try headers as fallback
    if not api_key and 'headers' in event:
        api_key = event['headers'].get('x-api-key') or event['headers'].get('Authorization', '').replace('Bearer ', '')
    
    # Try request body
    if not api_key:
        try:
            if 'body' in event:
                body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
                api_key = body.get('apikey')
        except:
            pass
    
    if api_key:
        user_info = get_user_from_api_key(api_key)
        if user_info:
            return user_info['user_id'], user_info['tier'], user_info
    
    # Fallback to IP-based identification for anonymous users
    source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
    user_agent = event.get('headers', {}).get('User-Agent', '')
    fingerprint = f"{source_ip}_{hash(user_agent) % 10000}"
    
    return fingerprint, 'anonymous', None

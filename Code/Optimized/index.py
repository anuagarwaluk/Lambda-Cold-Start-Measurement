# OPTIMIZED LAMBDA - BEST PRACTICES DEMONSTRATION
# This function demonstrates proper cold start optimization techniques

# BEST PRACTICE 1: Only import what you need at global scope

import json
import os
import boto3
from datetime import datetime


print("Loading only necessary libraries...")


# BEST PRACTICE 2: Create AWS clients at global scope for reuse
# This will INCREASE Cold Start, but save lot of time for warm executions
# You don't want to create new connection on every execution
# This shows balance between cold start and ongoing performance

print("Creating AWS clients at global scope for reuse...")

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


print("Global initialization complete - minimal and efficient!")


def lambda_handler(event, context):

    print(f"Handler started for {os.environ.get('FUNCTION_TYPE', 'UNKNOWN')} function")
    
    # BEST PRACTICE 3: Conditional logic inside handler, not global scope
    # Only process data when actually needed
    if event.get('process_data', True):
        print("Processing data conditionally inside handler...")
        # Minimal processing - only what's needed
        processed_items = 100  # Simulated light processing
    else:
        processed_items = 0
    
    try:
        # Get/update invocation count using pre-initialized client
        response = table.get_item(Key={'id': f"stats_{os.environ['FUNCTION_TYPE']}"})
        
        if 'Item' in response:
            invocation_count = int(response['Item'].get('invocation_count', 0)) + 1
        else:
            invocation_count = 1
        
        table.put_item(
            Item={
                'id': f"stats_{os.environ['FUNCTION_TYPE']}",
                'invocation_count': invocation_count,
                'last_invocation': datetime.now().isoformat(),
                'student_name': os.environ['STUDENT_NAME'],
                'function_type': os.environ['FUNCTION_TYPE']
            }
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'{os.environ["FUNCTION_TYPE"]} Function Executed',
                'function_type': os.environ['FUNCTION_TYPE'],
                'student_name': os.environ['STUDENT_NAME'],
                'invocation_count': int(invocation_count),
                'items_processed': processed_items,
                'optimization_techniques': [
                    'Only necessary imports at global scope',
                    'AWS clients created globally for reuse',
                    'No unnecessary global computation',
                    'No sleep delays',
                    'Conditional processing inside handler'
                ]
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Function execution failed'
            })
        }

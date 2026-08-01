# PROVISIONED CONCURRENCY LAMBDA - THE EXPENSIVE FIX
# Identical bad code to high-coldstart/index.py.
# The ONLY difference is deployment config: Provisioned Concurrency on Version 1.
# The init still costs ~6s - it just runs before the request arrives, not during it.

# BAD PRACTICE 1: Importing unused heavy libraries at global scope

import json
import os
import time
import urllib3
import ssl
import hashlib
import base64
import gzip
import zipfile
import tarfile
import xml.etree.ElementTree as ET
import csv
import sqlite3
import boto3
from datetime import datetime
import random
import re
import uuid
import threading
import multiprocessing
import subprocess
import socket
import http.client
import ftplib
import smtplib
import imaplib
import poplib
import telnetlib
import urllib.request
import urllib.parse
import urllib.error


print("Loading heavy libraries and executing global code (but pre-warmed with provisioned concurrency)...")


# BAD PRACTICE 2: 5-second sleep in global scope - adds to every cold start
# Think of this as heavy code that should only run when needed

print("Sleeping for 5 seconds in global scope...")

time.sleep(5)


print("Global initialization complete with Provisioned Concurrency")


def lambda_handler(event, context):

    print(f"Handler started for {os.environ.get('FUNCTION_TYPE', 'UNKNOWN')} function")
    
    # BAD PRACTICE 4: Creating AWS clients inside handler (should be global)
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['TABLE_NAME'])
    
    try:
        # Get/update invocation count
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
                'performance_notes': [
                    'Same bad practices as high cold start function',
                    'But pre-warmed with provisioned concurrency',
                    'No cold start delay for users (costs money)',
                    'Better to optimize code AND use provisioned concurrency'
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

# AWS Lambda Cold Starts: What 5.3 Seconds Actually Costs
 
A measured comparison of three strategies for handling AWS Lambda cold starts. Three
functions, the same DynamoDB workload, the same runtime and memory. Every figure below comes
from a CloudWatch `REPORT` line — nothing modelled, nothing estimated.
 
**Environment:** `python3.11` · 512 MB · `us-east-1` · single DynamoDB table · July 2026
 
---
 
## Results
 
| Strategy | Function | Init duration | Handler duration | Billed duration |
|---|---|---|---|---|
| Do nothing | `high-coldstart` | 5,330.45 ms | 719.99 ms | **6,051 ms** |
| Pay to hide it | `provisioned-concurrency` | 6,160.85 ms <sup>1</sup> | 911.41 ms | **912 ms** <sup>2</sup> |
| Fix the code | `optimized` | 468.18 ms | 181.09 ms | **650 ms** |
 
<sup>1</sup> Ran 29 min 34 s *before* the request arrived, off the critical path.
<sup>2</sup> Per request. Provisioned capacity is billed separately, by the hour, whether or
not requests arrive.
 
**11.4× faster init. 9.3× lower billed duration. No additional infrastructure.**

<img width="3200" height="2216" alt="lambda-cold-start-timeline" src="https://github.com/user-attachments/assets/c57b068e-54f2-4825-8792-1ceb7a344d77" />

 
---
 
## The finding
 
On-demand Lambda bills for **INIT + execution**:
 
```
5,330 + 720 = 6,051 ms
  468 + 181 =   650 ms
```
 
A slow cold start is not only a latency complaint from your users. It is a line on the
invoice, on every cold invocation. That is the part that tends to go unnoticed, because the
`Duration` field in the console shows only the handler — the `Billed Duration` field, sitting
right next to it, is the one that includes initialisation.
 
---
 
## What differs between the three functions
 
| | `high-coldstart` | `provisioned-concurrency` | `optimized` |
|---|---|---|---|
| Imports at global scope | 30+ | 30+ — *identical code* | 4 |
| Blocking work at init | `time.sleep(5)` | `time.sleep(5)` | none |
| `boto3` client | created **inside** the handler | created **inside** the handler | created **once** at global scope |
| Deployment config | on-demand, `$LATEST` | Provisioned Concurrency on Version 1 | on-demand, `$LATEST` |
| Cost of the fix | — | pre-warmed capacity billed 24/7 | **zero** — it is a code change |
| Survives a traffic spike | no | only up to provisioned capacity | yes, at any scale |
 
<img width="3200" height="1750" alt="lambda-cold-start-comparison-table" src="https://github.com/user-attachments/assets/2d78df21-6e75-46b6-817e-f4ecb138d1e3" />

 
---
 
## The anti-pattern
 
```python
# Bad practice 1: ~30 heavy imports at global scope, almost none of them used.
import json, os, time, urllib3, ssl, hashlib, base64, gzip, zipfile, tarfile
import xml.etree.ElementTree as ET
import csv, sqlite3, boto3, random, re, uuid, threading, multiprocessing
import subprocess, socket, http.client, ftplib, smtplib, imaplib, poplib
from datetime import datetime
 
# Bad practice 2: blocking work at global scope.
# Stands in for a real ML model load, schema fetch, or connection pool warm-up.
time.sleep(5)
 
def lambda_handler(event, context):
    # Bad practice 3: the client is rebuilt on EVERY invocation, warm ones included.
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['TABLE_NAME'])
    ...
```
 
Everything outside `lambda_handler` runs during the INIT phase. INIT runs on every cold
start. On on-demand Lambda, INIT is billed.
 
## The fix
 
```python
# Only what is actually used.
import json
import os
import boto3
from datetime import datetime
 
# Created ONCE per execution environment, then reused for the container's entire life.
# This makes cold start slightly WORSE (~160 ms here) and is still the right call.
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])
 
def lambda_handler(event, context):
    # Conditional work belongs in the handler, not at global scope.
    if event.get('process_data', True):
        processed_items = 100
    else:
        processed_items = 0
    ...
```
 
### Why the client placement matters more than it looks
 
`boto3.resource('dynamodb')` inside the handler rebuilds the connection on **every**
invocation — warm ones included, roughly 200–400 ms each, indefinitely. Moving it to global
scope pays that cost once per execution environment and reuses it for the container's whole
life, typically many requests.
 
This is the one optimisation that makes cold start measurably *worse* and is still correct.
In the timestamps below it cost 162 ms of init to save a comparable amount on every warm
invocation afterwards.
 
---
 
## Evidence
 
### `high-coldstart` — cold, 512 MB
 
```
INIT_START Runtime Version: python:3.11.mainlinev2.v18
13:39:15.875Z  Loading heavy libraries and executing global code...
13:39:15.875Z  Sleeping for 5 seconds in global scope...
13:39:20.875Z  Global initialization complete.
13:39:20.880Z  START RequestId: 04e1e5ef-5eb4-47ce-84db-1b943dc69605
13:39:21.605Z  END RequestId: 04e1e5ef-5eb4-47ce-84db-1b943dc69605
REPORT  Duration: 719.99 ms | Billed Duration: 6051 ms | Memory Size: 512 MB
        Max Memory Used: 94 MB | Init Duration: 5330.45 ms
```
<img width="1451" height="626" alt="01-high-coldstart-code-imports" src="https://github.com/user-attachments/assets/b39fda85-b0e3-42d3-a27b-e065578880be" />

 
### `provisioned-concurrency` — Version 1, 512 MB
 
Initialisation, running ahead of any request:
 
```
13:26:52.274Z  INIT_START
13:26:53.434Z  Loading heavy libraries and executing global code
               (but pre-warmed with provisioned concurrency)...
13:26:53.434Z  Sleeping for 5 seconds in global scope...
13:26:58.434Z  Global initialization complete with Provisioned Concurrency
13:26:58.435Z  INIT_REPORT Init Duration: 6160.85 ms
```
 
The request, **29 minutes and 34 seconds later**:
 
```
13:56:32.643Z  START RequestId: 57df2441-04b1-45ea-bd4a-d7736250d190 Version: 1
13:56:33.555Z  END RequestId: 57df2441-04b1-45ea-bd4a-d7736250d190
REPORT  Duration: 911.41 ms | Billed Duration: 912 ms | Memory Size: 512 MB
```
 
Two details worth reading closely:
 
1. The init is **slower** here (6,160 ms vs 5,330 ms). The work did not get cheaper. It moved.
2. The `REPORT` line carries no `Init Duration`, and the timestamps are half an hour apart.
   That gap is exactly what the money buys — and you pay for it continuously.
### `optimized` — cold, 512 MB
 
```
14:03:33.351Z  INIT_START
14:03:33.656Z  Loading only necessary libraries...
14:03:33.656Z  Creating AWS clients at global scope for reuse...
14:03:33.818Z  Global initialization complete - minimal and efficient!
14:03:33.823Z  START RequestId: f82e71fe-091b-423b-8672-a832a6531623
14:03:34.005Z  END RequestId: f82e71fe-091b-423b-8672-a832a6531623
REPORT  Duration: 181.09 ms | Billed Duration: 650 ms | Memory Size: 512 MB
        Max Memory Used: 92 MB | Init Duration: 468.18 ms
```
 
The timestamps break that 468 ms init down usefully:
 
- **305 ms** — importing the four required libraries
- **162 ms** — creating the DynamoDB resource and table handle at global scope
---
 
## Two things the exercise didn't ask for
 
### 1. The warm invocation is why cold starts hide
 
The same unoptimised function, invoked again into a live execution environment:
 
```
REPORT  Duration: 108.56 ms | Billed Duration: 109 ms | Memory Size: 512 MB
```
 
No `Init Duration` line. Invoke a function twice during testing and it looks fast. The
6-second path is the one your first real user hits — and the one every user hits after a
quiet period.
 
### 2. Memory is CPU
 
I re-ran the unoptimised function at 128 MB instead of 512 MB:
 
| Memory | Init duration | Handler duration | Billed duration |
|---|---|---|---|
| 512 MB | 5,330.45 ms | 719.99 ms | 6,051 ms |
| 128 MB | 5,302.64 ms | **2,965.54 ms** | 8,269 ms |
 
Handler time went **4× slower** because Lambda scales CPU allocation with configured memory.
Init barely moved, because it is dominated by `time.sleep(5)` — a wall-clock wait, not a
CPU-bound operation.
 
Both halves matter. Cutting memory to save money made the function slower *and* the bill
larger. And no amount of extra memory will speed up sleeping or I/O waiting, which is where
a surprising share of real init time goes.
<img width="1730" height="820" alt="Screenshot 2026-08-01 at 15 48 47" src="https://github.com/user-attachments/assets/c38d2db9-853a-4826-b4e3-e0c3510c549c" />
<img width="1749" height="842" alt="Screenshot 2026-08-01 at 15 45 34" src="https://github.com/user-attachments/assets/cd228969-1b32-4704-9295-bdfcf8f4f8d2" />
<img width="1674" height="810" alt="Screenshot 2026-08-01 at 15 46 10" src="https://github.com/user-attachments/assets/613efaa6-49f3-45c0-80a6-b1890893c17a" />
<img width="1872" height="628" alt="Screenshot 2026-08-01 at 15 47 36" src="https://github.com/user-attachments/assets/60392007-f115-41ec-98b7-496e3aaa6e55" />
<img width="1850" height="550" alt="Screenshot 2026-08-01 at 15 47 51" src="https://github.com/user-attachments/assets/3f27104f-c417-40bd-9efa-7753389514a8" />
<img width="2278" height="577" alt="Screenshot 2026-08-01 at 15 48 11" src="https://github.com/user-attachments/assets/f47162dc-ae61-4623-a530-2cb5de13e0c2" />
<img width="2343" height="660" alt="09-provisioned-concurrency-cloudwatch" src="https://github.com/user-attachments/assets/4f5eaaad-9e4c-4f92-b1fe-9105243259fa" />
<img width="2635" height="735" alt="08-provisioned-concurrency-test-detail" src="https://github.com/user-attachments/assets/f27e5c98-f5a4-457a-a385-bb750a76510c" />

 
---
 
## The order that works
 
1. **Cut the global scope.** Free, and usually the largest single win.
2. **Move SDK clients and connections to global scope.** Accept ~200–400 ms more init to save
   it on every warm invocation afterwards.
3. **Add Provisioned Concurrency last**, only on latency-critical user-facing paths — and
   knowing it protects you only up to the concurrency you have paid for. Overflow requests
   still pay the full cold start.
Provisioned Concurrency applied to unoptimised code buys silence, not efficiency.
 
---
 
## Reproducing this
 
Deploy three functions with identical handlers against one DynamoDB table, varying only the
global scope and the deployment config. Force a cold start by redeploying, then read the
`REPORT` line:
 
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/high-coldstart-function \
  --filter-pattern "REPORT"
```
 
Two things that will cost you an afternoon if you miss them:
 
- **Provisioned Concurrency only attaches to a published version or alias**, never to
  `$LATEST`. If you still see an `Init Duration` on the provisioned function, you are
  invoking `$LATEST`.
- **Provisioned Concurrency bills continuously per instance**, independent of traffic. Tear
  it down when you have finished measuring.
## Caveats
 
- Single-invocation measurements, not averaged. Lambda init times vary between executions;
  treat the ratios as indicative rather than precise.
- `time.sleep(5)` dominates the unoptimised init and exaggerates the gap relative to a
  typical production function. The mechanism it illustrates — everything at global scope runs
  during INIT, and INIT is billed, is what generalises.

*Built and measured by Anu Agarwal — [linkedin.com/in/agarwalanu](https://www.linkedin.com/in/agarwalanu)*

<img width="732" height="56" alt="image" src="https://github.com/user-attachments/assets/6d6d2775-4fcf-45af-a872-aa3b19b7db72" />

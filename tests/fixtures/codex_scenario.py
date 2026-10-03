"""EXPLICIT TEST DOUBLE. Speaks JSONL; never invokes a model or executes a command."""
import json
import sys
import threading
import time
from pathlib import Path

root = str(Path(sys.argv[1]).resolve())
lock = threading.Lock()
turns = []
current = None
count = 0
pending = {}


def emit(value):
    with lock:
        sys.stdout.buffer.write((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()


def event(method, params):
    emit({'method': method, 'params': {'threadId': 'fixture-thread', **params}})


def finish(turn, status='completed'):
    if turn['status'] != 'inProgress':
        return
    turn['status'] = status
    item = {'type': 'agentMessage', 'id': turn['id']+'-answer', 'text': 'ТЕСТ: ответ без модели'}
    turn['items'].append(item)
    event('item/completed', {'item': item})
    event('turn/diff/updated', {'diff': '--- a/test.txt\n+++ b/test.txt\n-old\n+fixture\n'})
    event('turn/completed', {'turn': turn})


for line in sys.stdin.buffer:
    msg = json.loads(line)
    method, ident, params = msg.get('method'), msg.get('id'), msg.get('params') or {}
    if method is None:
        turn = pending.pop(ident, None)
        if turn:
            finish(turn, 'completed' if msg.get('result', {}).get('decision')=='accept' else 'interrupted')
        continue
    if method == 'initialized':
        continue
    result = {}
    if method == 'initialize': result={'userAgent':'explicit-fixture'}
    elif method == 'account/read': result={'account':{'type':'chatgpt'}}
    elif method == 'test/statistics': result={'sendCount':count}
    elif method == 'thread/list':result={'data':[{'id':'fixture-thread','cwd':root,'name':'Тестовый диалог'}], 'nextCursor':None}
    elif method in ('thread/start','thread/read','thread/resume'):result={'thread':{'id':'fixture-thread','cwd':root,'turns':turns}}
    elif method == 'turn/start':
        count += 1
        prompt=params['input'][0]['text']
        current={'id':f'fixture-turn-{count}','status':'inProgress','items':[{'type':'userMessage','id':f'u-{count}','content':[{'type':'text','text':prompt}]}]}
        turns.append(current)
        emit({'id':ident,'result':{'turn':{'id':current['id'],'status':'inProgress'}}})
        event('turn/started', {'turn':current})
        event('item/completed', {'item':current['items'][0]})
        event('item/agentMessage/delta', {'itemId':current['id']+'-answer','delta':'ТЕСТ: '})
        if 'approval' in prompt:
            key=f'approve-{count}';pending[key]=current
            emit({'id':key,'method':'item/commandExecution/requestApproval','params':{'threadId':'fixture-thread','turnId':current['id'],'command':'echo explicit-test-fixture'}})
        elif 'slow' not in prompt:
            finish(current)
        continue
    elif method == 'turn/interrupt':
        if current:finish(current,'interrupted')
    else:
        emit({'id':ident,'error':{'code':-32601,'message':'not in test fixture'}})
        continue
    emit({'id':ident,'result':result})

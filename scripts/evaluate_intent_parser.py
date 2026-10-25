"""Opt-in real Ollama parsing evaluation. Does not access camera or change notes.
Run: uv run python -m scripts.evaluate_intent_parser --model qwen3.5:4b
"""
import argparse
import asyncio
import json
from pathlib import Path
from backend.app.intent_parser import IntentParser, normalized
from backend.app.models import AssistantRequest
from backend.app.note_commands import clean_object_name


async def run(model):
    parser = IntentParser('http://127.0.0.1:11434', model)
    cases = json.loads((Path(__file__).parents[1] / 'backend/tests/fixtures/intent_utterances.json').read_text())
    failed = 0
    for case in cases:
        try:
            result = await parser.parse(AssistantRequest(message=case['message'], **case.get('context', {})), [])
            errors = []
            if result.action != case['action']:
                errors.append(f"action={result.action}")
            if 'comment' in case and normalized(' '.join(result.comment_spans)).rstrip('.!?') != normalized(case['comment']).rstrip('.!?'):
                errors.append(f'comment={result.comment_spans!r}')
            if 'name' in case and clean_object_name(result.object_name) != case['name']:
                errors.append(f'name={result.object_name!r}')
            for key in ('selector', 'number'):
                if key in case and getattr(result, key) != case[key]:
                    errors.append(f'{key}={getattr(result, key)!r}')
            if errors:
                raise ValueError(', '.join(errors))
            print('PASS', case['message'], flush=True)
        except Exception as error:
            failed += 1
            print('FAIL', case['message'], ':', error, flush=True)
    print(f'{len(cases)-failed}/{len(cases)} live parsing cases passed', flush=True)
    return failed


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--model', default='qwen3.5:4b')
    options = args.parse_args()
    raise SystemExit(1 if asyncio.run(run(options.model)) else 0)

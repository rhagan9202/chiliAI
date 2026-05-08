import json
import pathlib
import re
import subprocess
import sys

REPO = 'Fed-Incubator/Crushing-Fraud-XAI'
PROMPTS_DIR = pathlib.Path('/Users/rhagan/chiliAI/docs/planning/story_prompts')
SUMMARY_PATH = pathlib.Path('/tmp/chili_story_issues_created.json')


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, capture_output=True, text=True)


existing_raw = run_command([
    'gh', 'issue', 'list', '--repo', REPO, '--limit', '500', '--json', 'number,title'
]).stdout
existing = {item['title']: item['number'] for item in json.loads(existing_raw)}

files = sorted(PROMPTS_DIR.glob('SP_*_prompt.md'))
created: list[dict[str, object]] = []
skipped: list[dict[str, object]] = []

for index, path in enumerate(files, start=1):
    lines = path.read_text().splitlines()
    if not lines or not lines[0].startswith('# '):
        print(f'SKIP malformed file: {path.name}', file=sys.stderr)
        continue

    title = lines[0][2:].strip()
    if title in existing:
        skipped.append({'file': path.name, 'title': title, 'number': existing[title]})
        print(f'SKIPPED {index}/{len(files)}: #{existing[title]} {title}')
        continue

    result = run_command([
        'gh', 'issue', 'create', '--repo', REPO, '--title', title, '--body-file', str(path)
    ])
    output = result.stdout.strip()
    match = re.search(r'/issues/(\d+)$', output)
    number = int(match.group(1)) if match else None
    created.append({'file': path.name, 'title': title, 'number': number, 'url': output})
    print(f'CREATED {index}/{len(files)}: #{number} {title}')

SUMMARY_PATH.write_text(json.dumps({'created': created, 'skipped': skipped}, indent=2))
print(f'SUMMARY {SUMMARY_PATH}')
print(f'CREATED_COUNT {len(created)}')
print(f'SKIPPED_COUNT {len(skipped)}')

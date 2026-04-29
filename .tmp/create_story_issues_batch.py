import json
import pathlib
import re
import subprocess
import sys

REPO = 'Fed-Incubator/Crushing-Fraud-XAI'
PROMPTS_DIR = pathlib.Path('/Users/rhagan/chiliAI/docs/planning/story_prompts')
BATCH_LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def run_json(args: list[str]) -> list[dict[str, object]]:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


existing = {
    item['title']: item['number']
    for item in run_json(['gh', 'issue', 'list', '--repo', REPO, '--limit', '500', '--json', 'number,title'])
}

pending: list[pathlib.Path] = []
for path in sorted(PROMPTS_DIR.glob('SP_*_prompt.md')):
    lines = path.read_text().splitlines()
    if lines and lines[0].startswith('# '):
        title = lines[0][2:].strip()
        if title not in existing:
            pending.append(path)

print(f'PENDING {len(pending)}')
for index, path in enumerate(pending[:BATCH_LIMIT], start=1):
    title = path.read_text().splitlines()[0][2:].strip()
    result = subprocess.run(
        ['gh', 'issue', 'create', '--repo', REPO, '--title', title, '--body-file', str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    match = re.search(r'/issues/(\d+)$', output)
    number = int(match.group(1)) if match else None
    print(f'CREATED {index}/{min(BATCH_LIMIT, len(pending))}: #{number} {title}')

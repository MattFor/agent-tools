import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'forge-diff')

# A fake gh/tea: prints the canned answer of the first rule whose args are all among the call's args; logs every call.
FAKE = """#!@PY@
import json, sys
args = sys.argv[1:]
try:
	seen = [json.loads(x) for x in open('@LOG@')]
except OSError:
	seen = []
with open('@LOG@', 'a') as f:
	f.write(json.dumps(args) + '\\n')
for r in json.load(open('@DB@')):
	if all(t in args for t in r['args']):
		out = r.get('out', '')
		if not isinstance(out, str):
			out = json.dumps([out] if '--slurp' in args else out)
		print(out)
		sys.stderr.write(r.get('err', ''))
		sys.exit(r.get('rc', 0))
sys.stderr.write('fake: no rule for ' + ' '.join(args))
sys.exit(99)
"""
NOT_FOUND = {'message': "The target couldn't be found.", 'url': 'https://codeberg.org/api/swagger', 'errors': []}
WRITES = ('-X', '--method', '-f', '-F', '--field', '--raw-field', '-d', '--data')


def repo(private=True, archived=False, branch='master', desc: str | None = 'A tool', topics=('cli', 'agents')):
	return {
		'private': private,
		'archived': archived,
		'default_branch': branch,
		'description': desc,
		'topics': list(topics),
	}


def refs(shas, key):
	return [{'name': n, 'commit': {key: s}} for n, s in shas.items()]


class ForgeDiff(unittest.TestCase):
	def setUp(self):
		self.d = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.d)

	def fake(self, name, rules):
		db, exe = os.path.join(self.d, f'{name}.db'), os.path.join(self.d, name)
		with open(db, 'w') as f:
			json.dump([*rules, {'args': ['auth', 'status']}], f)
		with open(exe, 'w') as f:
			f.write(FAKE.replace('@PY@', sys.executable).replace('@LOG@', f'{exe}.log').replace('@DB@', db))
		os.chmod(exe, 0o755)

	def gh(self, name, r, branches, tags):
		self.fake(
			'gh',
			[
				{'args': [f'repos/{name}'], 'out': r},
				{'args': [f'repos/{name}/branches'], 'out': refs(branches, 'sha')},
				{'args': [f'repos/{name}/tags'], 'out': refs(tags, 'sha')},
			],
		)

	def tea(self, name, r, branches, tags):
		page = '?limit=50&page=1'
		self.fake(
			'tea',
			[
				{'args': [f'repos/{name}'], 'out': r},
				{'args': [f'repos/{name}/branches{page}'], 'out': refs(branches, 'id')},
				{'args': [f'repos/{name}/tags{page}'], 'out': refs(tags, 'sha')},
			],
		)

	def run_tool(self, *args, **env):
		env = {**{k: v for k, v in os.environ.items() if k != 'CODEBERG_TOKEN'}, 'PATH': self.d, **env}
		return subprocess.run([sys.executable, BIN, *args], capture_output=True, text=True, env=env, check=False)

	def calls(self, name):
		with open(os.path.join(self.d, f'{name}.log')) as f:
			return [json.loads(x) for x in f]

	def test_match_is_ok_and_read_only(self):
		heads, tags = {'master': 'a' * 40, 'dev': 'b' * 40}, {'v1': 'c' * 40}
		# None and '' are both "no description"; topic order does not matter.
		self.gh('o/r', repo(desc=None, topics=['agents', 'cli']), heads, tags)
		self.tea('o/r', repo(desc='', topics=['cli', 'agents']), heads, tags)
		r = self.run_tool('o/r', '--tea-login', 'L')
		self.assertEqual((r.returncode, r.stdout), (0, 'ok    o/r\n'), r.stderr)
		calls = self.calls('gh') + self.calls('tea')
		self.assertTrue(all(c[0] in ('api', 'auth') for c in self.calls('gh')))
		self.assertTrue(all(c[:3] == ['api', '--login', 'L'] for c in self.calls('tea')))
		self.assertFalse([a for c in calls for a in c if a in WRITES])

	def test_every_kind_of_difference(self):
		self.gh(
			'o/r',
			repo(private=True, archived=False, branch='main', desc='One', topics=['a', 'b']),
			{'main': '1a2b3c4' + '0' * 33, 'old': 'f' * 40, 'same': 'e' * 40},
			{'v1': 'c' * 40, 'v2': 'd' * 40},
		)
		self.tea(
			'o/r',
			repo(private=False, archived=True, branch='master', desc='Two', topics=['a']),
			{'main': '9f8e7d6' + '0' * 33, 'new': '7' * 40, 'same': 'e' * 40},
			{'v1': '1' * 40},
		)
		r = self.run_tool('o/r', '--tea-login', 'L')
		self.assertEqual(r.returncode, 1, r.stderr)
		self.assertEqual(
			r.stdout.splitlines(),
			[
				'DIFF  o/r',
				'    visibility: github private codeberg public',
				'    archived: github no codeberg yes',
				'    default branch: github main codeberg master',
				'    description differs',
				'    topics: github [a b] codeberg [a]',
				'    branch main: github 1a2b3c4 codeberg 9f8e7d6',
				'    branch new: github missing codeberg 7777777',
				'    branch old: github fffffff codeberg missing',
				'    tag v1: github ccccccc codeberg 1111111',
				'    tag v2: github ddddddd codeberg missing',
			],
		)

	def test_missing_repos(self):
		self.fake('tea', [{'args': ['repos/o/only-here'], 'out': NOT_FOUND}])
		self.fake(
			'gh',
			[
				{'args': ['repos/o/gone'], 'rc': 1, 'err': 'gh: Not Found (HTTP 404)'},
				{'args': ['repos/o/only-here'], 'out': repo()},
				{'args': ['repos/o/only-here/branches'], 'out': []},
				{'args': ['repos/o/only-here/tags'], 'out': []},
			],
		)
		r = self.run_tool('o/gone', 'o/only-here', '--tea-login', 'L')
		self.assertEqual(r.returncode, 1, r.stderr)
		self.assertEqual(
			r.stdout.splitlines(),
			['DIFF  o/gone', '    missing on github', 'DIFF  o/only-here', '    missing on codeberg'],
		)

	def test_pages_are_all_read(self):
		heads = {f'b{i:02}': f'{i:040x}' for i in range(60)}
		self.gh('o/r', repo(), heads, {})
		names = list(heads)
		page = '?limit=50&page='
		self.fake(
			'tea',
			[
				{'args': ['repos/o/r'], 'out': repo()},
				{'args': [f'repos/o/r/branches{page}1'], 'out': refs({n: heads[n] for n in names[:50]}, 'id')},
				{'args': [f'repos/o/r/branches{page}2'], 'out': refs({n: heads[n] for n in names[50:]}, 'id')},
				{'args': [f'repos/o/r/tags{page}1'], 'out': []},
			],
		)
		r = self.run_tool('o/r', '--tea-login', 'L')
		self.assertEqual((r.returncode, r.stdout), (0, 'ok    o/r\n'), r.stderr)

	def test_owner_codeberg_owner_and_env_login(self):
		self.fake(
			'gh',
			[
				{'args': ['repo', 'list', 'o'], 'out': [{'nameWithOwner': 'o/r'}]},
				{'args': ['repos/o/r'], 'out': repo()},
				{'args': ['repos/o/r/branches'], 'out': []},
				{'args': ['repos/o/r/tags'], 'out': []},
			],
		)
		self.tea('mirror/r', repo(), {}, {})
		r = self.run_tool('--owner', 'o', '--codeberg-owner', 'mirror', FORGE_DIFF_TEA_LOGIN='FromEnv')
		self.assertEqual((r.returncode, r.stdout), (0, 'ok    o/r\n'), r.stderr)
		self.assertEqual(self.calls('tea')[0][:3], ['api', '--login', 'FromEnv'])
		(call,) = (c for c in self.calls('gh') if c[:2] == ['repo', 'list'])
		self.assertTrue({'--no-archived', '--source'} <= set(call))

	def test_http_with_and_without_token(self):
		data = {
			'/api/v1/repos/o/r': repo(),
			'/api/v1/repos/o/r/branches?limit=50&page=1': refs({'master': 'a' * 40}, 'id'),
			'/api/v1/repos/o/r/tags?limit=50&page=1': [],
		}
		seen = []

		class Handler(http.server.BaseHTTPRequestHandler):
			def do_GET(self):
				seen.append(self.headers.get('Authorization'))
				body = data.get(self.path) if seen[-1] == 'token T0K' else None
				self.send_response(404 if body is None else 200)
				self.end_headers()
				self.wfile.write(json.dumps(body).encode())

			def log_message(self, format, *args):
				pass

		srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
		threading.Thread(target=srv.serve_forever, daemon=True).start()
		self.addCleanup(srv.server_close)
		self.addCleanup(srv.shutdown)
		self.gh('o/r', repo(), {'master': 'a' * 40}, {})
		host = f'http://127.0.0.1:{srv.server_address[1]}'
		r = self.run_tool('o/r', '--host', host)
		self.assertEqual(r.returncode, 1)
		self.assertIn('missing on codeberg (checked anonymously', r.stdout)
		self.assertEqual(seen, [None])
		r = self.run_tool('o/r', '--host', host, CODEBERG_TOKEN='T0K')
		self.assertEqual((r.returncode, r.stdout), (0, 'ok    o/r\n'), r.stderr)
		self.assertEqual(seen[1:], ['token T0K'] * 3)

	def test_setup_errors(self):
		r = self.run_tool('o/r', '--tea-login', 'L')
		self.assertEqual(r.returncode, 2)
		self.assertIn('gh', r.stderr)
		self.fake('gh', [{'args': ['auth', 'status'], 'rc': 1, 'err': 'You are not logged into any GitHub hosts.'}])
		r = self.run_tool('o/r', '--tea-login', 'L')
		self.assertEqual(r.returncode, 2)
		self.assertIn('not logged in', r.stderr)
		self.gh('o/r', repo(), {}, {})
		self.fake('tea', [{'args': ['api'], 'rc': 1, 'err': "Error: login name 'L' does not exist"}])
		r = self.run_tool('o/r', '--tea-login', 'L')
		self.assertEqual(r.returncode, 2)
		self.assertIn('does not exist', r.stderr)
		self.assertEqual(self.run_tool('nonsense').returncode, 2)


if __name__ == '__main__':
	unittest.main()

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'gh-dependabot')

# A fake gh: prints the canned answer of the first rule whose args are all among the call's args; logs every call.
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
		n = sum(all(t in s for t in r['args']) for s in seen)
		outs = r.get('outs') or [r.get('out', '')]
		out = outs[min(n, len(outs) - 1)]
		print(out if isinstance(out, str) else json.dumps(out))
		sys.stderr.write(r.get('err', ''))
		sys.exit(r.get('rc', 0))
sys.stderr.write('fake: no rule for ' + ' '.join(args))
sys.exit(99)
"""


def check(x):
	if x.startswith('ctx:'):
		return {'__typename': 'StatusContext', 'state': x[4:]}
	if x in ('IN_PROGRESS', 'QUEUED'):
		return {'__typename': 'CheckRun', 'status': x, 'conclusion': ''}
	return {'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': x}


def pr(n, login='app/dependabot', checks=('SUCCESS',), mergeable='MERGEABLE', state='CLEAN'):
	return {
		'number': n,
		'title': f'Bump dep{n} from 1 to 2',
		'author': {'is_bot': True, 'login': login},
		'mergeable': mergeable,
		'mergeStateStatus': state,
		'url': f'https://github.com/o/r/pull/{n}',
		'statusCheckRollup': [check(c) for c in checks],
	}


def cols(out):
	return [re.split(r'\s{2,}', x) for x in out.splitlines() if not x.startswith(' ')]


class GhDependabot(unittest.TestCase):
	def setUp(self):
		self.d = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.d)
		self.log = os.path.join(self.d, 'gh.log')

	def gh(self, rules):
		db = os.path.join(self.d, 'gh.db')
		with open(db, 'w') as f:
			json.dump([*rules, {'args': ['auth', 'status']}], f)
		exe = os.path.join(self.d, 'gh')
		with open(exe, 'w') as f:
			f.write(FAKE.replace('@PY@', sys.executable).replace('@LOG@', self.log).replace('@DB@', db))
		os.chmod(exe, 0o755)

	def run_tool(self, *args):
		env = {**os.environ, 'PATH': self.d}
		return subprocess.run([sys.executable, BIN, *args], capture_output=True, text=True, env=env, check=False)

	def calls(self, *prefix):
		with open(self.log) as f:
			return [c for c in map(json.loads, f) if c[: len(prefix)] == list(prefix)]

	def prs(self, *lists, repo='o/r'):
		self.gh([{'args': ['pr', 'list', repo], 'outs': list(lists)}, {'args': ['pr', 'merge']}])

	def test_classify_and_bot_names(self):
		self.prs(
			[
				pr(1, checks=['SUCCESS', 'NEUTRAL', 'SKIPPED']),
				pr(2, checks=['SUCCESS', 'FAILURE'], state='UNSTABLE'),
				pr(3, checks=['SUCCESS', 'IN_PROGRESS']),
				pr(4, checks=['ctx:SUCCESS', 'ctx:PENDING']),
				pr(5, checks=[]),
				pr(6, login='dependabot[bot]', checks=['ctx:ERROR'], mergeable='CONFLICTING', state='DIRTY'),
				pr(7, login='app/renovate', checks=['CANCELLED'], state='BEHIND'),
				pr(8, login='MattFor'),
				pr(9, login='app/github-actions'),
			]
		)
		r = self.run_tool('o/r')
		self.assertEqual(r.returncode, 1, r.stderr)
		self.assertEqual(
			cols(r.stdout),
			[
				['o/r #1', 'pass', 'CLEAN', 'Bump dep1 from 1 to 2'],
				['o/r #2', 'FAIL', 'UNSTABLE', 'Bump dep2 from 1 to 2'],
				['o/r #3', 'pending', 'CLEAN', 'Bump dep3 from 1 to 2'],
				['o/r #4', 'pending', 'CLEAN', 'Bump dep4 from 1 to 2'],
				['o/r #5', 'none', 'CLEAN', 'Bump dep5 from 1 to 2'],
				['o/r #6', 'FAIL', 'DIRTY', 'Bump dep6 from 1 to 2'],
				['o/r #7', 'FAIL', 'BEHIND', 'Bump dep7 from 1 to 2'],
			],
		)
		self.assertEqual(self.calls('pr', 'merge'), [])
		r = self.run_tool('o/r', '--bots', 'app/Renovate')
		self.assertEqual([c[0] for c in cols(r.stdout)], ['o/r #7'])

	def test_green_list_exits_0_and_nothing_to_list(self):
		self.prs([pr(1), pr(2, checks=['ctx:SUCCESS']), pr(3, checks=[])])
		self.assertEqual(self.run_tool('o/r').returncode, 0)
		self.prs([pr(8, login='MattFor')])
		r = self.run_tool('o/r')
		self.assertEqual(r.returncode, 0)
		self.assertIn('no open pull requests', r.stdout)

	def test_merge_only_what_is_ready(self):
		many = [
			pr(1),
			pr(2, checks=['FAILURE']),
			pr(3, checks=['IN_PROGRESS']),
			pr(4, checks=[]),
			pr(5, mergeable='CONFLICTING', state='DIRTY'),
			pr(6, state='BLOCKED'),
			pr(8),
		]
		# Each merge is followed by a re-read of the repo.
		self.prs(many, [p for p in many if p['number'] != 1], [p for p in many if p['number'] not in (1, 8)])
		r = self.run_tool('o/r', '--merge')
		self.assertEqual(r.returncode, 1, r.stderr)
		self.assertEqual(
			self.calls('pr', 'merge'),
			[
				['pr', 'merge', '1', '-R', 'o/r', '--squash', '--delete-branch'],
				['pr', 'merge', '8', '-R', 'o/r', '--squash', '--delete-branch'],
			],
		)
		self.assertEqual(len(self.calls('pr', 'list')), 3)
		self.assertIn('  #1 merged (squash)', r.stdout)
		self.assertIn('  #2 skipped: checks FAIL', r.stdout)
		self.assertIn('  #3 skipped: checks pending', r.stdout)
		self.assertIn('  #4 skipped: no checks', r.stdout)
		self.assertIn('  #5 skipped: conflicting, the bot will rebase', r.stdout)
		self.assertIn('  #6 skipped: merge state BLOCKED', r.stdout)

	def test_no_checks_ok_and_method(self):
		self.prs([pr(4, checks=[])], [])
		r = self.run_tool('o/r', '--merge', '--no-checks-ok', '--method', 'rebase')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(self.calls('pr', 'merge'), [['pr', 'merge', '4', '-R', 'o/r', '--rebase', '--delete-branch']])

	def test_conflict_after_a_merge_is_left_to_the_bot(self):
		self.prs([pr(1), pr(2)], [pr(2, mergeable='CONFLICTING', state='DIRTY')])
		r = self.run_tool('o/r', '--merge')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(len(self.calls('pr', 'merge')), 1)
		self.assertIn('  #2 skipped: conflicting now, the bot will rebase', r.stdout)

	def test_unknown_mergeability_is_read_again(self):
		self.prs([pr(1), pr(2)], [pr(2, mergeable='UNKNOWN', state='UNKNOWN')], [pr(2)], [])
		r = self.run_tool('o/r', '--merge')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual([c[2] for c in self.calls('pr', 'merge')], ['1', '2'])

	def test_failed_merge_exits_1_and_goes_on(self):
		self.gh(
			[
				{'args': ['pr', 'list', 'o/r'], 'out': [pr(1), pr(2)]},
				{'args': ['pr', 'merge'], 'rc': 1, 'err': 'Pull request is not mergeable'},
			]
		)
		r = self.run_tool('o/r', '--merge')
		self.assertEqual(r.returncode, 1)
		self.assertIn('#1 merge FAILED: Pull request is not mergeable', r.stdout)
		self.assertEqual(len(self.calls('pr', 'merge')), 2)

	def test_owner_lists_repos_and_a_bad_repo_exits_2(self):
		self.gh(
			[
				{'args': ['repo', 'list', 'o'], 'out': [{'nameWithOwner': 'o/a'}, {'nameWithOwner': 'o/b'}]},
				{'args': ['pr', 'list', 'o/a'], 'rc': 1, 'err': 'boom'},
				{'args': ['pr', 'list', 'o/b'], 'out': [pr(1)]},
			]
		)
		r = self.run_tool('--owner', 'o')
		self.assertEqual(r.returncode, 2)
		self.assertIn('o/a: boom', r.stderr)
		self.assertIn('o/b #1', r.stdout)
		(call,) = self.calls('repo', 'list')
		self.assertTrue({'--no-archived', '--source'} <= set(call))

	def test_repo_of_the_current_folder(self):
		self.gh(
			[
				{'args': ['repo', 'view'], 'out': {'nameWithOwner': 'o/here'}},
				{'args': ['pr', 'list', 'o/here'], 'out': [pr(1)]},
			]
		)
		r = self.run_tool()
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('o/here #1', r.stdout)

	def test_setup_errors(self):
		r = self.run_tool('o/r')
		self.assertEqual(r.returncode, 2)
		self.assertIn('gh', r.stderr)
		self.gh([{'args': ['auth', 'status'], 'rc': 1, 'err': 'You are not logged into any GitHub hosts.'}])
		r = self.run_tool('o/r')
		self.assertEqual(r.returncode, 2)
		self.assertIn('not logged in', r.stderr)
		self.assertEqual(self.run_tool('nonsense').returncode, 2)


if __name__ == '__main__':
	unittest.main()

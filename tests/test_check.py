import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'check')
MASON = os.path.expanduser('~/.local/share/nvim/mason/bin')


def have(tool):
	return shutil.which(tool) or shutil.which(tool, path=MASON)


def write(path, text, mode=0o644):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, 'w') as f:
		f.write(text)
	os.chmod(path, mode)


class Check(unittest.TestCase):
	def setUp(self):
		self.d = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.d)
		self.bin = os.path.join(self.d, 'stubs')
		os.makedirs(self.bin)

	def repo(self, name, files):
		root = os.path.join(self.d, name)
		os.makedirs(root)
		for rel, text in files.items():
			write(os.path.join(root, rel), text)
		return root

	def stub(self, name, body):
		write(os.path.join(self.bin, name), f'#!/bin/sh\n{body}\n', 0o755)

	def stubbed(self):
		"""An environment where only the stubs exist, and mason's bin is not found."""
		return {'PATH': self.bin, 'HOME': self.d}

	def run_check(self, *args, env=None, cwd=None):
		return subprocess.run(
			[sys.executable, BIN, *args], check=False, capture_output=True, text=True, env=env, cwd=cwd
		)

	@unittest.skipUnless(have('ruff'), 'ruff not installed')
	def test_ruff_ok_and_fail(self):
		r = self.run_check(self.repo('ok', {'a.py': 'x = 1\n'}))
		self.assertEqual(r.returncode, 0, r.stdout)
		self.assertRegex(r.stdout, r'(?m)^ok   ruff check  \(\d+\.\ds\)$')
		self.assertRegex(r.stdout, r'(?m)^ok   ruff format --check  \(\d+\.\ds\)$')
		r = self.run_check(self.repo('bad', {'a.py': 'import os\n'}))
		self.assertEqual(r.returncode, 1)
		self.assertRegex(r.stdout, r'(?m)^FAIL ruff check  \(\d+\.\ds\)$')
		self.assertRegex(r.stdout, r'(?m)^ok   ruff format --check  ')
		self.assertIn('\n    F401', r.stdout)

	@unittest.skipUnless(have('ruff'), 'ruff not installed')
	def test_fix(self):
		root = self.repo('bad', {'a.py': 'import os\n'})
		r = self.run_check(root, '--fix')
		self.assertEqual(r.returncode, 0, r.stdout)
		self.assertIn('ok   ruff check --fix  (', r.stdout)
		self.assertIn('ok   ruff format  (', r.stdout)
		with open(os.path.join(root, 'a.py')) as f:
			self.assertEqual(f.read(), '')

	@unittest.skipUnless(have('shellcheck') and have('shfmt'), 'shellcheck or shfmt not installed')
	def test_shell(self):
		root = self.repo('sh', {})
		write(os.path.join(root, 'bin', 'run'), '#!/bin/sh\necho $1\n', 0o755)
		write(os.path.join(root, 'notes.txt'), 'echo $1\n')
		r = self.run_check(root)
		self.assertEqual(r.returncode, 1)
		self.assertRegex(r.stdout, r'(?m)^FAIL shellcheck  \(')
		self.assertIn('SC2086', r.stdout)
		self.assertRegex(r.stdout, r'(?m)^ok   shfmt -d  \(')

	def test_missing_tools_are_skipped(self):
		root = self.repo('mixed', {'Cargo.toml': '', 'a.py': 'x = 1\n', 'pyrightconfig.json': '{}', 'tests/t.py': ''})
		r = self.run_check(root, env=self.stubbed())
		self.assertEqual(r.returncode, 0, r.stdout)
		lines = r.stdout.splitlines()
		for name in (
			'cargo fmt --check',
			'cargo clippy --all-targets -- -D warnings',
			'cargo test',
			'ruff check',
			'ruff format --check',
			'basedpyright',
			'python3 -m unittest discover -s tests',
		):
			self.assertIn(f'skip {name}  (not installed)', lines)
		self.assertEqual(len(lines), 7)

	def test_package_scripts(self):
		files = {
			'package.json': '{"scripts": {"lint": "x", "test": "y", "start": "z"}}',
			'pnpm-lock.yaml': '',
			'.prettierrc': '{}',
		}
		root = self.repo('js', files)
		self.stub('pnpm', '[ "$2" = lint ] && { echo lint broke; exit 1; }\necho all good')
		r = self.run_check(root, env=self.stubbed())
		self.assertEqual(r.returncode, 1)
		self.assertRegex(r.stdout, r'(?m)^FAIL pnpm run lint  \(\d+\.\ds\)\n    lint broke\nok   pnpm run test  \(')
		# Prettier is never downloaded: no local install is a skipped step.
		self.assertIn('skip prettier --check .  (not installed)', r.stdout)
		self.assertNotIn('start', r.stdout)
		self.assertNotIn('all good', r.stdout)
		r = self.run_check(root, '--only', 'test', '-v', env=self.stubbed())
		self.assertEqual(r.returncode, 0, r.stdout)
		self.assertEqual(len(r.stdout.splitlines()), 2)
		self.assertIn('    all good', r.stdout)

	def test_only_test_runs_unittest(self):
		root = self.repo(
			'py',
			{
				'a.py': 'import os\n',
				'tests/test_a.py': 'import unittest\n\n\nclass A(unittest.TestCase):\n\tdef test_a(self):\n\t\tpass\n',
			},
		)
		r = self.run_check(root, '--only', 'test')
		self.assertEqual(r.returncode, 0, r.stdout)
		self.assertRegex(r.stdout, r'^ok   python3 -m unittest discover -s tests  \(\d+\.\ds\)\n$')

	@unittest.skipUnless(shutil.which('git'), 'git not installed')
	def test_default_dir_is_git_toplevel(self):
		root = self.repo('top', {'Cargo.toml': '', 'sub/x.txt': ''})
		subprocess.run(['git', 'init', '-q', root], check=True)
		self.stub('cargo', 'exit 0')
		self.stub('git', f'exec {shutil.which("git")} "$@"')
		r = self.run_check(env=self.stubbed(), cwd=os.path.join(root, 'sub'))
		self.assertEqual(r.returncode, 0, r.stdout)
		self.assertEqual(r.stdout.count('ok   cargo '), 3)

	def test_usage_errors_and_nothing_to_check(self):
		self.assertEqual(self.run_check('--only', 'bogus').returncode, 2)
		r = self.run_check(os.path.join(self.d, 'missing'))
		self.assertEqual(r.returncode, 2)
		self.assertIn('No such file', r.stderr)
		r = self.run_check(self.repo('empty', {}))
		self.assertEqual(r.returncode, 0)
		self.assertIn('nothing to check', r.stdout)


if __name__ == '__main__':
	unittest.main()
